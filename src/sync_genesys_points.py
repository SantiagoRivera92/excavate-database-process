import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import (
    get_mongo_client,
    fetch_genesys_points_from_yaml_yugi,
    parse_genesys_manual_updates,
    MONGO_URI,
)
from pymongo import UpdateOne


def _find_card_by_konami_id(collection, konami_id):
    for key in (konami_id, str(konami_id)):
        doc = collection.find_one({"_id": key}, {"_id": 1, "name.en": 1})
        if doc:
            return doc
    return None


def main():
    if not MONGO_URI:
        print("Error: MONGO_URI environment variable not set", flush=True)
        sys.exit(1)

    print("Connecting to MongoDB...", flush=True)
    client = get_mongo_client()
    cards_collection = client["Cards"].Cards

    print("Fetching Genesys points from yaml-yugi...", flush=True)
    yaml_yugi_points = fetch_genesys_points_from_yaml_yugi()
    print(f"Found {len(yaml_yugi_points)} pointed cards in yaml-yugi data", flush=True)

    manual_changes, manual_errors = parse_genesys_manual_updates()
    if manual_errors:
        print(f"WARNING: {len(manual_errors)} line(s) in the manual updates file could not be parsed", flush=True)
    if manual_changes:
        print(f"Applying {len(manual_changes)} manual override(s) on top of upstream data...", flush=True)
        manual_names = sorted({name for name, _, _ in manual_changes})
        name_to_ids = {}
        for doc in cards_collection.find({"name.en": {"$in": manual_names}}, {"_id": 1, "name.en": 1}):
            name_to_ids.setdefault(doc.get("name", {}).get("en"), []).append(doc["_id"])
        applied = 0
        missing = []
        for name, _old, new in manual_changes:
            ids = name_to_ids.get(name)
            if not ids:
                missing.append(name)
                continue
            for card_key in ids:
                try:
                    card_key = int(card_key)
                except (ValueError, TypeError):
                    pass
                if new > 0:
                    yaml_yugi_points[card_key] = new
                else:
                    yaml_yugi_points.pop(card_key, None)
                applied += 1
        print(f"Applied {applied} manual override(s) to {len(yaml_yugi_points)} pointed cards", flush=True)
        if missing:
            print(f"WARNING: {len(missing)} manual override name(s) not found in database:", flush=True)
            for name in missing:
                print(f"  {name}", flush=True)

    print("Fetching currently pointed cards from MongoDB...", flush=True)
    db_pointed_cursor = cards_collection.find(
        {"genesys_points": {"$gt": 0}},
        {"_id": 1, "name.en": 1, "genesys_points": 1},
    )
    db_pointed = {}
    for doc in db_pointed_cursor:
        konami_id = doc.get("_id")
        if konami_id is None:
            continue
        try:
            konami_id = int(konami_id)
        except (ValueError, TypeError):
            pass
        db_pointed[konami_id] = {
            "_id": doc["_id"],
            "name_en": doc.get("name", {}).get("en", ""),
            "current_points": doc.get("genesys_points", 0),
        }
    print(f"Found {len(db_pointed)} pointed cards in MongoDB", flush=True)

    updates = []
    changes = []

    for konami_id, info in db_pointed.items():
        if konami_id not in yaml_yugi_points:
            changes.append((info["name_en"], info["current_points"], 0))
            updates.append(UpdateOne({"_id": info["_id"]}, {"$set": {"genesys_points": 0}}))

    for konami_id, points in yaml_yugi_points.items():
        if konami_id in db_pointed:
            changes.append((db_pointed[konami_id]["name_en"], db_pointed[konami_id]["current_points"], points))
            if db_pointed[konami_id]["current_points"] != points:
                updates.append(UpdateOne({"_id": db_pointed[konami_id]["_id"]}, {"$set": {"genesys_points": points}}))
        else:
            found = _find_card_by_konami_id(cards_collection, konami_id)
            if found:
                name = found.get("name", {}).get("en", str(konami_id))
                changes.append((name, 0, points))
                updates.append(UpdateOne({"_id": found["_id"]}, {"$set": {"genesys_points": points}}))
            else:
                print(f"  WARNING: {konami_id} not found in database, cannot update points", flush=True)

    if changes:
        changes.sort(key=lambda c: -c[2])
        print(f"\nChanges ({len(changes)}):", flush=True)
        for name, old, new in changes:
            print(f"  {name}: {old} => {new}", flush=True)

    if updates:
        print(f"\nApplying {len(updates)} updates to MongoDB...", flush=True)
        result = cards_collection.bulk_write(updates, ordered=False)
        print(f"Matched: {result.matched_count}, Modified: {result.modified_count}", flush=True)
    else:
        print("No updates needed", flush=True)


if __name__ == "__main__":
    main()
