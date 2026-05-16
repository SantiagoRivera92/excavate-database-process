import time
from pathlib import Path
from common import (
    BASE_DIR, StepTimer, save_json_file, fetch_json_from_url,
    get_localized_value, get_mongo_client, get_card_print_images_collection,
    load_initial_data, transform_basic_card_info, process_card_sets,
    update_card_statuses, add_videogame_data, add_banlist_history,
    add_md_banlist_history, assign_genesys_points,
    get_card_gallery, assign_image_urls_and_upload,
    list_s3_files_in_webp, list_s3_art_files_in_webp,
    download_transform_and_upload_card_image,
    merge_dm_and_arkana, merge_poly_and_fusion,
    DATASET_URL, OUTPUT_PATH, CACHE_DIR, ARKANA_DM_ID, FUSION_ID,
    load_touched_map, save_touched_map, batch_get_gallery_touched,
)
from meta_dump import dump_all
import pymongo


def main():
    print("Monthly full refresh starting...", flush=True)
    total_start = time.time()

    with StepTimer("connect_mongodb"):
        client = get_mongo_client()
        cards_collection = client["Cards"].Cards
        card_print_images_collection = get_card_print_images_collection(client)

    with StepTimer("load_touched_map"):
        touched_map = load_touched_map()
        print(f"Loaded touched data for {len(touched_map)} gallery pages")

    with StepTimer("load_initial_data"):
        loaded_data = load_initial_data(update_videogame_data=True)

    with StepTimer("list_s3_files"):
        s3_webp_files = list_s3_files_in_webp()
        s3_art_files = list_s3_art_files_in_webp()
        print(f"S3 webp: {len(s3_webp_files)}, art: {len(s3_art_files)}")

    with StepTimer("download_cards_dataset"):
        print("Downloading main card dataset...")
        raw_card_dataset = fetch_json_from_url(DATASET_URL)
        print(f"Downloaded {len(raw_card_dataset)} cards")

    # Build gallery name mapping and check which need refresh
    name_to_gallery = {}
    for raw_card in raw_card_dataset:
        names = get_localized_value(raw_card, "name")
        if not names or "en" not in names:
            continue
        card_name_en = names["en"]
        konami_id = raw_card.get("konami_id")
        gallery_card_name = card_name_en
        if konami_id == ARKANA_DM_ID:
            gallery_card_name = "Dark Magician (Arkana)"
        elif konami_id == FUSION_ID:
            gallery_card_name = "Polymerization (alternate password)"
        name_to_gallery[card_name_en] = gallery_card_name

    with StepTimer("batch_check_touched"):
        all_gallery_names = list(name_to_gallery.values())
        current_touched = batch_get_gallery_touched(all_gallery_names)
        cards_needing_refresh = {
            name for name, gname in name_to_gallery.items()
            if current_touched.get(gname, "") != touched_map.get(gname, "")
        }
        print(f"Cards needing gallery refresh: {len(cards_needing_refresh)} / {len(raw_card_dataset)}")

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

        print(f"Processing: {card_name_en}")

        if "text" in raw_card:
            transformed_card["text"] = get_localized_value(raw_card, "text")
        if "pendulum_effect" in raw_card:
            transformed_card["pendulum_effect"] = get_localized_value(raw_card, "pendulum_effect")

        with StepTimer("process_card_sets"):
            processed_sets = process_card_sets(raw_card.get("sets", {}), card_name_en, loaded_data)
            transformed_card["sets"] = processed_sets

        gallery_card_name = name_to_gallery[card_name_en]

        assign_genesys_points(transformed_card, loaded_data["genesys_points"])

        if card_name_en in cards_needing_refresh:
            with StepTimer("get_card_gallery"):
                gallery_info, gallery_touched = get_card_gallery(gallery_card_name, use_cache=True)
                if gallery_touched:
                    touched_map[gallery_card_name] = gallery_touched
        else:
            gallery_info, _ = get_card_gallery(gallery_card_name, use_cache=True)

        with StepTimer("assign_images_and_upload"):
            assign_image_urls_and_upload(transformed_card, gallery_info, s3_webp_files, card_print_images_collection)

        with StepTimer("update_status"):
            update_card_statuses(transformed_card, loaded_data, raw_card.get("limit_regulation", {}))
        with StepTimer("add_videogame_data"):
            add_videogame_data(transformed_card, loaded_data)

        if card_name_en in loaded_data.get("artwork_urls_map", {}):
            transformed_card["artwork_urls"] = loaded_data["artwork_urls_map"][card_name_en]

        add_banlist_history(transformed_card, loaded_data)
        add_md_banlist_history(transformed_card, loaded_data)

        processed_cards.append(transformed_card)

        elapsed = time.time() - card_start
        print(f"  [{elapsed:.2f}s]")

    with StepTimer("merge_cards"):
        processed_cards = merge_dm_and_arkana(processed_cards)
        processed_cards = merge_poly_and_fusion(processed_cards)
        processed_cards.sort(key=lambda c: c.get("name", {}).get("en", ""))

    with StepTimer("save_touched_map"):
        save_touched_map(touched_map)

    with StepTimer("save_json"):
        save_json_file(processed_cards, OUTPUT_PATH)
        print(f"Saved {len(processed_cards)} cards to {OUTPUT_PATH}")

    with StepTimer("upload_missing_arts"):
        print("Uploading missing card arts...")
        for card in processed_cards:
            card_password = card["_id"]
            output_path = Path(BASE_DIR, "temp_images", f"{str(card_password)}.webp")
            filename = f"art/{card_password}.webp"
            if filename not in s3_art_files:
                print(f'Uploading art for {card["name"]["en"]}')
                download_transform_and_upload_card_image(card, output_path)

    with StepTimer("write_to_mongodb"):
        ops = []
        for card in processed_cards:
            if card.get("image_url") is None:
                continue
            ops.append(pymongo.ReplaceOne({"_id": card["_id"]}, card, upsert=True))
        if ops:
            result = cards_collection.bulk_write(ops, ordered=False)
            print(f"MongoDB: upserted {result.upserted_count}, modified {result.modified_count}")

    total_elapsed = time.time() - total_start
    print(f"\n[TIMING] Total: {total_elapsed:.3f}s")


if __name__ == "__main__":
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    main()
