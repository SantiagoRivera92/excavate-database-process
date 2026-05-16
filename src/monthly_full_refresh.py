import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
import pymongo

_THREAD_WORKERS = 8


def _process_single_card(raw_card, name_to_gallery, cards_needing_refresh, loaded_data,
                          s3_webp_files, card_print_images_collection, touched_map,
                          touched_map_lock):
    card_start = time.time()
    transformed_card = {}
    names = get_localized_value(raw_card, "name")
    if not names or "en" not in names:
        return None
    transformed_card["name"] = names
    card_name_en = names["en"]
    konami_id = raw_card.get("konami_id")

    if not transform_basic_card_info(raw_card, transformed_card):
        return None

    print(f"Processing: {card_name_en}", flush=True)

    if "text" in raw_card:
        transformed_card["text"] = get_localized_value(raw_card, "text")
    if "pendulum_effect" in raw_card:
        transformed_card["pendulum_effect"] = get_localized_value(raw_card, "pendulum_effect")

    processed_sets = process_card_sets(raw_card.get("sets", {}), card_name_en, loaded_data)
    transformed_card["sets"] = processed_sets

    gallery_card_name = name_to_gallery[card_name_en]

    assign_genesys_points(transformed_card, loaded_data["genesys_points"])

    if card_name_en in cards_needing_refresh:
        gallery_info, gallery_touched = get_card_gallery(gallery_card_name, use_cache=True)
        if gallery_touched:
            with touched_map_lock:
                touched_map[gallery_card_name] = gallery_touched
    else:
        gallery_info, _ = get_card_gallery(gallery_card_name, use_cache=True)

    assign_image_urls_and_upload(transformed_card, gallery_info, s3_webp_files, card_print_images_collection)

    update_card_statuses(transformed_card, loaded_data, raw_card.get("limit_regulation", {}))
    add_videogame_data(transformed_card, loaded_data)

    if card_name_en in loaded_data.get("artwork_urls_map", {}):
        transformed_card["artwork_urls"] = loaded_data["artwork_urls_map"][card_name_en]

    add_banlist_history(transformed_card, loaded_data)
    add_md_banlist_history(transformed_card, loaded_data)

    elapsed = time.time() - card_start
    print(f"  [{card_name_en}] [{elapsed:.2f}s]", flush=True)
    return transformed_card


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
    touched_map_lock = threading.Lock()

    with StepTimer("process_cards"):
        with ThreadPoolExecutor(max_workers=_THREAD_WORKERS) as executor:
            futures = {
                executor.submit(
                    _process_single_card, raw_card, name_to_gallery,
                    cards_needing_refresh, loaded_data, s3_webp_files,
                    card_print_images_collection, touched_map, touched_map_lock
                ): raw_card
                for raw_card in raw_card_dataset
            }
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    processed_cards.append(result)

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
        def _upload_art(card):
            card_password = card["_id"]
            output_path = Path(BASE_DIR, "temp_images", f"{str(card_password)}.webp")
            filename = f"art/{card_password}.webp"
            if filename not in s3_art_files:
                print(f'Uploading art for {card["name"]["en"]}')
                download_transform_and_upload_card_image(card, output_path)
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(_upload_art, processed_cards)

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
