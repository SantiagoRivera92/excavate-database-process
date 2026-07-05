"""Find and fix cards whose main image is Japanese but have English prints with images."""

import sys
from common import get_mongo_client

PRIORITY_RARITIES = ["Common", "Rare", "Super Rare", "Ultra Rare", "Secret Rare"]


def pick_best_en_image(en_prints):
    best = None
    for p in en_prints:
        if p.get("image_url") and p.get("rarity") in PRIORITY_RARITIES and p.get("art_id") == 1 and "LART" not in p.get("set_number", ""):
            best = p["image_url"].split("/")[-1]
            break
    if not best:
        for p in en_prints:
            if p.get("image_url"):
                best = p["image_url"].split("/")[-1]
                break
    return best


def main(dry_run=True):
    client = get_mongo_client()
    cards_collection = client["Cards"].Cards

    query = {"image_url": {"$regex": "-JP-", "$options": "i"}}
    total = cards_collection.count_documents(query)
    print(f"Found {total} cards with Japanese main images")

    if total == 0:
        return

    cursor = cards_collection.find(
        query,
        {"name.en": 1, "image_url": 1, "sets.en": 1},
    )

    fixed = 0
    no_en_images = 0
    no_en_prints = 0

    for card in cursor:
        card_name = card.get("name", {}).get("en", "Unknown")
        en_prints = card.get("sets", {}).get("en", [])

        if not en_prints:
            no_en_prints += 1
            continue

        best_en = pick_best_en_image(en_prints)
        if not best_en:
            no_en_images += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] {card_name}: {card['image_url']} -> {best_en}")
            fixed += 1
        else:
            cards_collection.update_one(
                {"_id": card["_id"]},
                {"$set": {"image_url": best_en}},
            )
            print(f"  Fixed: {card_name}: {card['image_url']} -> {best_en}")
            fixed += 1

    print(f"\nResults:")
    print(f"  Fixed: {fixed}")
    print(f"  No English prints: {no_en_prints}")
    print(f"  English prints but no images: {no_en_images}")
    print(f"  Total processed: {fixed + no_en_prints + no_en_images}")


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("DRY RUN mode. Use --apply to apply changes.\n")
    main(dry_run=dry_run)
