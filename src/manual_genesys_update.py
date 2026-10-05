import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import (
    get_mongo_client,
    parse_genesys_manual_updates,
    MONGO_URI,
    GENESYS_MANUAL_UPDATES_FILE,
)
from pymongo import UpdateOne

DEFAULT_FILE = GENESYS_MANUAL_UPDATES_FILE


def main():
    parser = argparse.ArgumentParser(
        description="Apply manual Genesys point changes to MongoDB by card name."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=str(DEFAULT_FILE),
        help=f"Changes file in 'Card Name old->new' format (default: {DEFAULT_FILE})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing to MongoDB")
    parser.add_argument("--mongo-uri", default=MONGO_URI, help="MongoDB connection string (default: MONGO_URI env var)")
    args = parser.parse_args()

    if not args.mongo_uri:
        print("Error: MONGO_URI environment variable not set and --mongo-uri not provided", flush=True)
        sys.exit(1)

    path = Path(args.file)
    if not path.exists():
        print(f"Error: changes file not found: {path}", flush=True)
        sys.exit(1)

    changes, errors = parse_genesys_manual_updates(path)
    if errors:
        print(f"Error: could not parse {len(errors)} line(s):", flush=True)
        for lineno, raw in errors:
            print(f"  line {lineno}: {raw}", flush=True)
        sys.exit(1)

    print(f"Parsed {len(changes)} changes from {path}", flush=True)

    client = get_mongo_client()
    cards_collection = client["Cards"].Cards

    updates = []
    not_found = []
    for name, old, new in changes:
        docs = list(cards_collection.find({"name.en": name}, {"_id": 1, "genesys_points": 1}))
        if not docs:
            not_found.append(name)
            continue
        for doc in docs:
            current = doc.get("genesys_points", 0)
            marker = "" if current == old else f"  (expected old {old})"
            print(f"  {name}: {current} => {new}{marker}", flush=True)
            updates.append(UpdateOne({"_id": doc["_id"]}, {"$set": {"genesys_points": new}}))

    if not_found:
        print(f"\n{len(not_found)} name(s) not found in database:", flush=True)
        for name in not_found:
            print(f"  {name}", flush=True)

    if args.dry_run:
        print(f"\nDry run: {len(updates)} update(s) would be applied", flush=True)
        return

    if updates:
        print(f"\nApplying {len(updates)} update(s) to MongoDB...", flush=True)
        result = cards_collection.bulk_write(updates, ordered=False)
        print(f"Matched: {result.matched_count}, Modified: {result.modified_count}", flush=True)
    else:
        print("\nNo updates to apply", flush=True)


if __name__ == "__main__":
    main()
