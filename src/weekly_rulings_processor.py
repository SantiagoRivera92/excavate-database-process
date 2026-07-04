import time
import requests
import pymongo
from datetime import datetime, timezone
from common import get_mongo_client

RULINGS_API_URL = "https://db.ygoresources.com/data/card/{}"
MANIFEST_URL = "https://db.ygoresources.com/manifest/{}"
USER_AGENT = "excavate-database-process/1.0 (rulings cache; weekly sync)"
REQUEST_DELAY = 0.5
BATCH_SIZE = 100

STATE_DOC_ID = "_revision_state"


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
        response = requests.get(
            url, timeout=30, headers={"User-Agent": USER_AGENT}
        )
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


def get_current_cache_revision():
    url = RULINGS_API_URL.format(4007)
    try:
        response = requests.get(
            url, timeout=30, headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()
        return int(response.headers.get("X-Cache-Revision", "0"))
    except requests.exceptions.RequestException as e:
        print(f"Error getting cache revision: {e}", flush=True)
        raise SystemExit(f"Failed to get cache revision") from e


def get_changed_card_ids(manifest_url):
    try:
        response = requests.get(
            manifest_url, timeout=30, headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()
        manifest = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching manifest: {e}", flush=True)
        return set()

    return _extract_card_ids_from_manifest(manifest)


def _extract_card_ids_from_manifest(node, path_parts=None):
    if path_parts is None:
        path_parts = []

    ids = set()

    if isinstance(node, dict):
        for key, value in node.items():
            new_path = path_parts + [key]
            if (
                len(new_path) == 3
                and new_path[0] == "data"
                and new_path[1] == "card"
                and key.isdigit()
            ):
                ids.add(int(key))
            else:
                ids.update(_extract_card_ids_from_manifest(value, new_path))

    return ids


def process_card_ids(konami_ids, rulings_collection):
    processed = 0
    with_rulings = 0
    without_rulings = 0
    batch = []
    total_start = time.time()
    next_print = time.time() + 15

    for konami_id in konami_ids:
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

    return with_rulings, without_rulings


def main():
    print("Weekly rulings processor starting...", flush=True)
    total_start = time.time()

    client = get_mongo_client()
    cards_collection = client["Cards"].Cards
    rulings_collection = client["Cards"].Rulings

    current_revision = get_current_cache_revision()
    print(f"Current cache revision: {current_revision}", flush=True)

    state = rulings_collection.find_one({"_id": STATE_DOC_ID})
    previous_revision = state.get("revision", 0) if state else 0

    if previous_revision == 0:
        print("No previous revision found. Performing full sync...", flush=True)
        konami_ids = []
        for doc in cards_collection.find({}, {"_id": 1}):
            konami_ids.append(doc["_id"])
        print(f"Found {len(konami_ids)} cards to process", flush=True)

        with_rulings, without_rulings = process_card_ids(konami_ids, rulings_collection)

    elif current_revision <= previous_revision:
        print(
            f"No changes since last sync (revision {previous_revision} -> {current_revision})",
            flush=True,
        )
        with_rulings = 0
        without_rulings = 0
        konami_ids = []

    else:
        manifest_url = MANIFEST_URL.format(previous_revision)
        print(
            f"Fetching manifest for revisions {previous_revision + 1} -> {current_revision}...",
            flush=True,
        )
        changed_ids = get_changed_card_ids(manifest_url)
        print(f"Found {len(changed_ids)} changed card ids in manifest", flush=True)

        if not changed_ids:
            print("No card data changes in this revision range", flush=True)
            with_rulings = 0
            without_rulings = 0
            konami_ids = []
        else:
            all_konami_ids = set()
            for doc in cards_collection.find({"_id": {"$in": list(changed_ids)}}, {"_id": 1}):
                all_konami_ids.add(doc["_id"])

            missing = changed_ids - all_konami_ids
            if missing:
                print(
                    f"  Note: {len(missing)} changed cards are not in our Cards collection "
                    f"(likely pre-release or Asian-English exclusives)",
                    flush=True,
                )

            konami_ids = sorted(all_konami_ids)
            print(
                f"  {len(konami_ids)} of {len(changed_ids)} changed cards are in our database",
                flush=True,
            )

            with_rulings, without_rulings = process_card_ids(konami_ids, rulings_collection)

    rulings_collection.replace_one(
        {"_id": STATE_DOC_ID},
        {
            "_id": STATE_DOC_ID,
            "revision": current_revision,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        upsert=True,
    )

    total_elapsed = time.time() - total_start
    print(f"\nRulings processing complete in {total_elapsed:.1f}s", flush=True)
    print(f"  Total cards processed: {len(konami_ids)}", flush=True)
    print(f"  With rulings: {with_rulings}", flush=True)
    print(f"  Without rulings: {without_rulings}", flush=True)


if __name__ == "__main__":
    main()
