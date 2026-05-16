import time
from datetime import datetime, timedelta
from pathlib import Path
from common import (
    BASE_DIR, SET_EQUIVALENCES, SUPPORTED_LANGUAGES, EXCLUDED_FROM_DIAGNOSTIC_ERRORS,
    StepTimer, get_mongo_client, get_card_print_images_collection,
    upsert_card_print_image, list_s3_files_in_webp,
    get_card_gallery, find_image_for_printing,
    download_transform_and_upload_image, s3_url_from_raw,
    CACHE_DIR, ARKANA_DM_ID, FUSION_ID,
    load_touched_map, save_touched_map,
)


def get_cards_with_missing_recent_images(cards_collection, lookback_days=365):
    cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    pipeline = [
        {"$match": {
            "sets.en": {
                "$elemMatch": {
                    "print_date": {"$gte": cutoff},
                    "image_url": None,
                }
            }
        }},
        {"$project": {"name.en": 1, "card_id": 1, "_id": 1, "sets.en": 1}},
    ]
    cards = list(cards_collection.aggregate(pipeline))
    print(f"Found {len(cards)} cards with recent printings missing images")
    return cards


def patch_card_sets_in_mongodb(cards_collection, konami_id, set_number, rarity, art_id, image_url):
    result = cards_collection.update_one(
        {"_id": konami_id, "sets.en.set_number": set_number},
        {"$set": {
            "sets.en.$[elem].image_url": image_url,
            "sets.en.$[elem].file": image_url.split("/")[-1],
        }},
        array_filters=[{"elem.set_number": set_number, "elem.rarity": rarity, "elem.art_id": art_id}],
    )
    if result.modified_count == 0:
        cards_collection.update_one(
            {"_id": konami_id},
            {"$set": {"sets.en.$[elem].image_url": image_url}},
            array_filters=[{"elem.set_number": set_number}],
        )


def main():
    print("Daily image updater starting...", flush=True)
    total_start = time.time()

    with StepTimer("connect_mongodb"):
        client = get_mongo_client()
        cards_collection = client["Cards"].Cards
        card_print_images_collection = get_card_print_images_collection(client)

    with StepTimer("list_s3_files"):
        s3_webp_files = list_s3_files_in_webp()
        print(f"S3 webp files: {len(s3_webp_files)}")

    with StepTimer("load_touched_map"):
        touched_map = load_touched_map()
        print(f"Loaded touched data for {len(touched_map)} gallery pages")

    with StepTimer("find_cards_missing_images"):
        cards_to_process = get_cards_with_missing_recent_images(cards_collection, lookback_days=365)

    images_uploaded = 0
    for card in cards_to_process:
        card_name_en = card.get("name", {}).get("en")
        if not card_name_en:
            continue

        print(f"Fetching gallery for: {card_name_en}")

        gallery_card_name = card_name_en
        cid = card.get("card_id")
        if cid == ARKANA_DM_ID:
            gallery_card_name = "Dark Magician (Arkana)"
        elif cid == FUSION_ID:
            gallery_card_name = "Polymerization (alternate password)"

        with StepTimer(f"gallery_{card_name_en[:20]}"):
            gallery_info, gallery_touched = get_card_gallery(gallery_card_name, use_cache=True)
            if gallery_touched:
                touched_map[gallery_card_name] = gallery_touched

        if not gallery_info:
            print(f"  No gallery found")
            continue

        en_prints = card.get("sets", {}).get("en", [])
        for printing in en_prints:
            if printing.get("image_url") is not None:
                continue

            # Skip excluded sets
            if any(ex in printing.get("set_number", "") for ex in EXCLUDED_FROM_DIAGNOSTIC_ERRORS):
                continue

            raw_url = find_image_for_printing(printing, gallery_info, "en")
            if not raw_url:
                continue

            s3_url, s3_key = s3_url_from_raw(raw_url)
            if s3_key in s3_webp_files:
                print(f"  Already in S3: {s3_key}")
                # Still update MongoDB and CardPrintImages
            else:
                print(f"  Downloading and uploading: {raw_url}")
                output_path = Path(BASE_DIR, "temp_images", raw_url.split("/")[-1])
                if not download_transform_and_upload_image(raw_url, output_path):
                    print(f"  Failed to process image")
                    continue
                s3_webp_files.add(s3_key)
                images_uploaded += 1

            # Update CardPrintImages
            set_name_norm = SET_EQUIVALENCES.get(printing["set_name"], printing["set_name"])
            upsert_card_print_image(
                card_print_images_collection,
                printing["set_number"], set_name_norm,
                printing["rarity"], printing.get("art_id", 1),
                printing.get("suffix", ""), s3_url,
            )

            # Patch the card in Cards collection
            patch_card_sets_in_mongodb(
                cards_collection, card["_id"],
                printing["set_number"], printing["rarity"],
                printing.get("art_id", 1), s3_url,
            )
            print(f"  Patched: {printing['set_number']} -> {s3_url}")

    print(f"\nTotal images uploaded: {images_uploaded}")

    with StepTimer("save_touched_map"):
        save_touched_map(touched_map)

    total_elapsed = time.time() - total_start
    print(f"[TIMING] Total: {total_elapsed:.3f}s")


if __name__ == "__main__":
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    main()
