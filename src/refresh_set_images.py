"""Re-download every image of a set from Yugipedia and overwrite it in R2.

Usage:
    python src/refresh_set_images.py --set-code RA04
    python src/refresh_set_images.py --set-code MAMS --dry-run
"""

import argparse
import re
import sys
import time
from pathlib import Path

import requests

from common import (
    BASE_DIR,
    SET_EQUIVALENCES,
    SUPPORTED_LANGUAGES,
    StepTimer,
    download_transform_and_upload_image,
    get_card_print_images_collection,
    get_mongo_client,
    s3_url_from_raw,
    upsert_card_print_image,
)

API_URL = "https://yugipedia.com/api.php"
API_HEADERS = {"User-Agent": "Excavate by DiamondDude/1.0 (https://www.excavate.top)"}
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
THUMB_PREFIX_RE = re.compile(r"^\d+px-")


def normalize_set_code(set_code):
    return set_code.strip().upper()


def matches_set_code(set_number, set_code):
    return bool(set_number) and set_number.upper().startswith(set_code)


def fetch_cards_for_set(cards_collection, set_code):
    regex = f"^{re.escape(set_code)}"
    query = {
        "$or": [
            {f"sets.{lang}.set_number": {"$regex": regex, "$options": "i"}}
            for lang in SUPPORTED_LANGUAGES
        ]
    }
    projection = {"name.en": 1, "image_url": 1, "sets": 1}
    cards = list(cards_collection.find(query, projection))
    cards.sort(key=lambda card: card.get("name", {}).get("en", ""))
    return cards


def image_base_name(image_url):
    file_name = image_url.rsplit("/", 1)[-1]
    stem = file_name.rsplit(".", 1)[0]
    return THUMB_PREFIX_RE.sub("", stem)


def normalized_title(title):
    return title.replace("_", " ").strip().lower()


def fetch_image_info(base_names):
    titles_by_base = {
        base: [f"File:{base}{ext}" for ext in IMAGE_EXTENSIONS]
        for base in sorted(base_names)
    }
    title_to_base = {
        normalized_title(title): base
        for base, titles in titles_by_base.items()
        for title in titles
    }

    all_titles = [title for titles in titles_by_base.values() for title in titles]
    image_info = {}

    for index in range(0, len(all_titles), 40):
        batch = all_titles[index:index + 40]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url|size",
            "format": "json",
            "formatversion": "2",
        }

        for attempt in range(5):
            try:
                response = requests.get(
                    API_URL, params=params, headers=API_HEADERS, timeout=60
                )
                if response.status_code in (429, 502, 503, 520):
                    time.sleep(5 * (attempt + 1))
                    continue
                response.raise_for_status()
                data = response.json()
                break
            except (requests.RequestException, ValueError):
                time.sleep(5 * (attempt + 1))
        else:
            print(f"  Failed to query image info for {len(batch)} titles", flush=True)
            continue

        for page in data.get("query", {}).get("pages", []):
            base = title_to_base.get(normalized_title(page.get("title", "")))
            if not base or page.get("missing") or not page.get("imageinfo"):
                continue
            info = page["imageinfo"][0]
            current = image_info.get(base)
            if current is None or info.get("width", 0) > current.get("width", 0):
                image_info[base] = info

    return image_info


def collect_image_jobs(cards, set_code):
    jobs = {}

    for card in cards:
        for lang, prints in card.get("sets", {}).items():
            for printing in prints:
                if not matches_set_code(printing.get("set_number"), set_code):
                    continue
                image_url = printing.get("image_url")
                if not image_url:
                    continue
                base = image_base_name(image_url)
                job = jobs.setdefault(
                    base,
                    {
                        "base": base,
                        "prints": [],
                        "old_file": image_url.rsplit("/", 1)[-1],
                    },
                )
                job["prints"].append((card, lang, printing))

    return list(jobs.values())


def patch_card_printing(cards_collection, card_id, lang, printing, image_url):
    file_name = image_url.split("/")[-1]
    array_filter = {
        "elem.set_number": printing["set_number"],
        "elem.rarity": printing["rarity"],
        "elem.art_id": printing.get("art_id", 1),
    }
    return cards_collection.update_one(
        {"_id": card_id},
        {
            "$set": {
                f"sets.{lang}.$[elem].image_url": image_url,
                f"sets.{lang}.$[elem].file": file_name,
            }
        },
        array_filters=[array_filter],
    )


def refresh_job(job, info, cards_collection, card_print_images_collection, dry_run):
    stats = {"uploaded": 0, "patched": 0, "main_fixed": 0}

    if not info:
        print(f"  Not found on Yugipedia: {job['old_file']}", flush=True)
        return stats, False

    raw_url = info["url"]
    s3_url, _ = s3_url_from_raw(raw_url)
    new_file = s3_url.rsplit("/", 1)[-1]
    size = f"{info.get('width', '?')}x{info.get('height', '?')}"

    if dry_run:
        print(f"  [DRY RUN] {job['old_file']} -> {new_file} ({size})", flush=True)
        for card, lang, printing in job["prints"]:
            old_url = printing.get("image_url")
            if old_url and old_url != s3_url:
                stats["patched"] += 1
                old_file = old_url.rsplit("/", 1)[-1]
                if card.get("image_url") == old_file:
                    stats["main_fixed"] += 1
        return stats, True

    output_path = Path(BASE_DIR, "temp_images", raw_url.rsplit("/", 1)[-1])
    if not download_transform_and_upload_image(raw_url, output_path):
        print(f"  Failed: {job['old_file']}", flush=True)
        return stats, False

    stats["uploaded"] += 1

    for card, lang, printing in job["prints"]:
        set_name = SET_EQUIVALENCES.get(printing["set_name"], printing["set_name"])
        upsert_card_print_image(
            card_print_images_collection,
            printing["set_number"],
            set_name,
            printing["rarity"],
            printing.get("art_id", 1),
            printing.get("suffix", ""),
            s3_url,
        )

        if printing.get("image_url") != s3_url:
            patch_card_printing(cards_collection, card["_id"], lang, printing, s3_url)
            stats["patched"] += 1
            old_url = printing.get("image_url")
            old_file = old_url.rsplit("/", 1)[-1] if old_url else None
            if old_file and card.get("image_url") == old_file:
                cards_collection.update_one(
                    {"_id": card["_id"], "image_url": old_file},
                    {"$set": {"image_url": new_file}},
                )
                card["image_url"] = new_file
                stats["main_fixed"] += 1

    print(f"  {job['old_file']} -> {new_file} ({size})", flush=True)
    return stats, True


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-code", required=True, help="Set code to refresh, e.g. RA04 or MAMS")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be uploaded")
    return parser.parse_args()


def main():
    args = parse_args()
    set_code = normalize_set_code(args.set_code)

    with StepTimer("connect_mongodb"):
        client = get_mongo_client()
        cards_collection = client["Cards"].Cards
        card_print_images_collection = get_card_print_images_collection(client)

    with StepTimer("find_cards"):
        cards = fetch_cards_for_set(cards_collection, set_code)
        print(f"Found {len(cards)} cards for set code {set_code}", flush=True)

    if not cards:
        print(f"No cards found for set code {set_code}", flush=True)
        raise SystemExit(1)

    with StepTimer("collect_images"):
        jobs = collect_image_jobs(cards, set_code)
        print(f"Found {len(jobs)} images for set code {set_code}", flush=True)

    if not jobs:
        print(f"No images found for set code {set_code}", flush=True)
        raise SystemExit(1)

    with StepTimer("lookup_images"):
        image_info = fetch_image_info([job["base"] for job in jobs])

    totals = {"uploaded": 0, "patched": 0, "main_fixed": 0, "not_found": 0}
    for index, job in enumerate(jobs, 1):
        print(f"[{index}/{len(jobs)}] {job['old_file']}", flush=True)
        stats, found = refresh_job(
            job,
            image_info.get(job["base"]),
            cards_collection,
            card_print_images_collection,
            args.dry_run,
        )
        for key in ("uploaded", "patched", "main_fixed"):
            totals[key] += stats[key]
        if not found:
            totals["not_found"] += 1

    print(
        f"Done: {totals['uploaded']} uploaded, {totals['patched']} DB entries patched, "
        f"{totals['main_fixed']} main images fixed, {totals['not_found']} not found",
        flush=True,
    )

    if totals["not_found"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
