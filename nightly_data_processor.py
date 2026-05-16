import time
from pathlib import Path
from common import (
    BASE_DIR, SET_EQUIVALENCES, SUPPORTED_LANGUAGES, EXCLUDED_SETS_TIME_WIZARD,
    StepTimer, load_json_file, save_json_file, fetch_json_from_url,
    get_localized_value, get_mongo_client, get_card_print_images_collection,
    get_image_lookup_from_collection, upsert_card_print_image,
    load_initial_data, transform_basic_card_info, process_card_sets,
    update_card_statuses, add_videogame_data, add_banlist_history,
    add_md_banlist_history, assign_genesys_points,
    get_card_gallery, find_image_for_printing,
    apply_image_urls_from_lookup,
    download_transform_and_upload_image, s3_url_from_raw,
    merge_dm_and_arkana, merge_poly_and_fusion,
    DATASET_URL, OUTPUT_PATH, ARKANA_DM_ID, FUSION_ID,
    REGULAR_DM_ID, POLY_ID, CACHE_DIR,
    load_touched_map, save_touched_map,
)
from meta_dump import dump_all
import pymongo


def main():
    total_start = time.time()

    with StepTimer("connect_mongodb"):
        client = get_mongo_client()
        cards_collection = client["Cards"].Cards
        card_print_images_collection = get_card_print_images_collection(client)

    with StepTimer("load_image_lookup"):
        image_lookup = get_image_lookup_from_collection(card_print_images_collection)

    # Bootstrap CardPrintImages from existing Cards data if empty
    if not image_lookup:
        print("CardPrintImages is empty. Bootstrapping from existing Cards collection...")
        with StepTimer("bootstrap_card_print_images"):
            count = 0
            for card in cards_collection.find({}, {"_id": 1, "sets": 1}):
                for lang, prints in card.get("sets", {}).items():
                    for p in prints:
                        if p.get("image_url"):
                            set_name_norm = SET_EQUIVALENCES.get(p["set_name"], p["set_name"])
                            key = (p["set_number"], set_name_norm, p["rarity"], p.get("art_id", 1))
                            if key not in image_lookup:
                                image_lookup[key] = p["image_url"]
                                upsert_card_print_image(
                                    card_print_images_collection,
                                    p["set_number"], set_name_norm,
                                    p["rarity"], p.get("art_id", 1),
                                    p.get("suffix", ""), p["image_url"],
                                )
                                count += 1
            print(f"Bootstrapped {count} entries into CardPrintImages")

    with StepTimer("load_touched_map"):
        touched_map = load_touched_map()
        print(f"Loaded touched data for {len(touched_map)} gallery pages")

    with StepTimer("load_existing_konami_ids"):
        existing_ids = set()
        for doc in cards_collection.find({}, {"_id": 1}):
            existing_ids.add(doc["_id"])
        print(f"Existing cards in MongoDB: {len(existing_ids)}")

    with StepTimer("load_initial_data"):
        loaded_data = load_initial_data(update_videogame_data=True)

    with StepTimer("download_cards_dataset"):
        print("Downloading main card dataset...")
        raw_card_dataset = fetch_json_from_url(DATASET_URL)
        print(f"Downloaded {len(raw_card_dataset)} cards")

    raw_card_dataset.sort(key=lambda card: card.get("name", {}).get("en", ""))
    processed_cards = []

    for raw_card in raw_card_dataset:
        card_start = time.time()
        transformed_card = {}
        names = get_localized_value(raw_card, "name")
        if not names or "en" not in names:
            continue
        transformed_card["name"] = names
        card_name_en = names["en"]
        konami_id = raw_card.get("konami_id")

        if not transform_basic_card_info(raw_card, transformed_card):
            continue

        is_new_card = konami_id not in existing_ids
        print(f"Processing: {card_name_en} (new={is_new_card})")

        if "text" in raw_card:
            transformed_card["text"] = get_localized_value(raw_card, "text")
        if "pendulum_effect" in raw_card:
            transformed_card["pendulum_effect"] = get_localized_value(raw_card, "pendulum_effect")

        with StepTimer("process_card_sets"):
            processed_sets = process_card_sets(raw_card.get("sets", {}), card_name_en, loaded_data)
            transformed_card["sets"] = processed_sets

        with StepTimer("apply_images"):
            apply_image_urls_from_lookup(transformed_card, image_lookup)

            # For new cards, fetch gallery and try to fill missing images
            if is_new_card:
                gallery_card_name = card_name_en
                cid = transformed_card.get("card_id")
                if cid == ARKANA_DM_ID:
                    gallery_card_name = "Dark Magician (Arkana)"
                elif cid == FUSION_ID:
                    gallery_card_name = "Polymerization (alternate password)"

                gallery_info, gallery_touched = get_card_gallery(gallery_card_name, use_cache=True)
                if gallery_touched:
                    touched_map[gallery_card_name] = gallery_touched
                if gallery_info:
                    for lang in SUPPORTED_LANGUAGES:
                        if lang not in transformed_card.get("sets", {}) or lang not in gallery_info:
                            continue
                        for printing in transformed_card["sets"][lang]:
                            if printing.get("image_url") is not None:
                                continue
                            raw_url = find_image_for_printing(printing, gallery_info, lang)
                            if raw_url:
                                s3_url, s3_key = s3_url_from_raw(raw_url)
                                output_path = Path(BASE_DIR, "temp_images", raw_url.split("/")[-1])
                                download_transform_and_upload_image(raw_url, output_path)
                                printing["image_url"] = s3_url

                                set_name_norm = SET_EQUIVALENCES.get(printing["set_name"], printing["set_name"])
                                upsert_card_print_image(
                                    card_print_images_collection,
                                    printing["set_number"], set_name_norm,
                                    printing["rarity"], printing.get("art_id", 1),
                                    printing.get("suffix", ""), s3_url,
                                )
                                image_lookup[(printing["set_number"], set_name_norm, printing["rarity"], printing.get("art_id", 1))] = s3_url

        with StepTimer("update_status"):
            update_card_statuses(transformed_card, loaded_data, raw_card.get("limit_regulation", {}))
        with StepTimer("add_videogame_data"):
            add_videogame_data(transformed_card, loaded_data)

        if card_name_en in loaded_data.get("artwork_urls_map", {}):
            transformed_card["artwork_urls"] = loaded_data["artwork_urls_map"][card_name_en]

        for lang_prints_key in list(transformed_card.get("sets", {}).keys()):
            for printing in transformed_card["sets"][lang_prints_key]:
                if printing.get("image_url"):
                    printing["file"] = printing["image_url"].split("/")[-1]

        add_banlist_history(transformed_card, loaded_data)
        add_md_banlist_history(transformed_card, loaded_data)
        assign_genesys_points(transformed_card, loaded_data["genesys_points"])

        processed_cards.append(transformed_card)

        elapsed = time.time() - card_start
        print(f"  [{elapsed:.2f}s]")

    with StepTimer("merge_cards"):
        processed_cards = merge_dm_and_arkana(processed_cards)
        processed_cards = merge_poly_and_fusion(processed_cards)
        processed_cards.sort(key=lambda c: c.get("name", {}).get("en", ""))

    with StepTimer("save_json"):
        save_json_file(processed_cards, OUTPUT_PATH)
        print(f"Saved {len(processed_cards)} cards to {OUTPUT_PATH}")

    with StepTimer("write_to_mongodb"):
        ops = []
        for card in processed_cards:
            if card.get("image_url") is None:
                continue
            ops.append(pymongo.ReplaceOne({"_id": card["_id"]}, card, upsert=True))
        if ops:
            result = cards_collection.bulk_write(ops, ordered=False)
            print(f"MongoDB: upserted {result.upserted_count}, modified {result.modified_count}")
        else:
            print("No cards to write to MongoDB")

    with StepTimer("save_touched_map"):
        save_touched_map(touched_map)

    total_elapsed = time.time() - total_start
    print(f"\n[TIMING] Total: {total_elapsed:.3f}s")


if __name__ == "__main__":
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    main()
