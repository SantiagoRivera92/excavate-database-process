import time
import requests
import pymongo
from datetime import datetime, timezone
from common import get_mongo_client

RULINGS_API_URL = "https://db.ygoresources.com/data/card/{}"
REQUEST_DELAY = 0.25
BATCH_SIZE = 100


def extract_english_entries(faq_data):
    entries = []
    raw_entries = faq_data.get("entries", {})
    for _key, group in raw_entries.items():
        en_items = [item["en"] for item in group if "en" in item and item["en"]]
        if not en_items:
            continue
        entries.append({
            "title": en_items[0],
            "body": en_items[1:],
        })
    return entries


def fetch_ruling_for_card(konami_id):
    url = RULINGS_API_URL.format(konami_id)
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching rulings for {konami_id}: {e}", flush=True)
        return None
    except ValueError as e:
        print(f"  Error parsing JSON for {konami_id}: {e}", flush=True)
        return None

    faq_data = data.get("faqData")
    if not faq_data or not faq_data.get("entries"):
        return None

    entries = extract_english_entries(faq_data)
    if not entries:
        return None

    return {
        "_id": konami_id,
        "konami_id": konami_id,
        "entries": entries,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main():
    print("Weekly rulings processor starting...", flush=True)
    total_start = time.time()

    client = get_mongo_client()
    cards_collection = client["Cards"].Cards
    rulings_collection = client["Cards"].Rulings

    print("Fetching all konami_ids from Cards collection...", flush=True)
    konami_ids = []
    for doc in cards_collection.find({}, {"_id": 1}):
        konami_ids.append(doc["_id"])
    print(f"Found {len(konami_ids)} cards", flush=True)

    processed = 0
    with_rulings = 0
    without_rulings = 0
    batch = []
    next_print = time.time() + 15

    for i, konami_id in enumerate(konami_ids):
        ruling_doc = fetch_ruling_for_card(konami_id)

        if ruling_doc is None:
            without_rulings += 1
        else:
            with_rulings += 1
            batch.append(pymongo.ReplaceOne(
                {"_id": ruling_doc["_id"]},
                ruling_doc,
                upsert=True,
            ))

        if len(batch) >= BATCH_SIZE:
            try:
                rulings_collection.bulk_write(batch, ordered=False)
            except pymongo.errors.BulkWriteError as e:
                print(f"  Bulk write error: {e}", flush=True)
            batch = []

        processed += 1

        if time.time() >= next_print:
            elapsed = time.time() - total_start
            pct = (processed / len(konami_ids)) * 100
            print(
                f"  Progress: {processed}/{len(konami_ids)} "
                f"({pct:.1f}%) | with: {with_rulings} | without: {without_rulings} | "
                f"elapsed: {elapsed:.0f}s",
                flush=True,
            )
            next_print = time.time() + 15

        time.sleep(REQUEST_DELAY)

    if batch:
        try:
            rulings_collection.bulk_write(batch, ordered=False)
        except pymongo.errors.BulkWriteError as e:
            print(f"  Bulk write error: {e}", flush=True)

    total_elapsed = time.time() - total_start
    print(f"\nRulings processing complete in {total_elapsed:.1f}s", flush=True)
    print(f"  Total cards: {len(konami_ids)}", flush=True)
    print(f"  With rulings: {with_rulings}", flush=True)
    print(f"  Without rulings: {without_rulings}", flush=True)


if __name__ == "__main__":
    main()
