import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import get_mongo_client, fetch_genesys_points_from_duelingnexus, MONGO_URI
from pymongo import UpdateOne


def _find_card_by_card_id(collection, card_id):
    for key in (card_id, str(card_id)):
        doc = collection.find_one({"card_id": key}, {"_id": 1, "name.en": 1})
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

    print("Fetching Genesys points from Dueling Nexus...", flush=True)
    nexus_points = fetch_genesys_points_from_duelingnexus()
    print(f"Found {len(nexus_points)} pointed cards in Dueling Nexus data", flush=True)

    print("Fetching currently pointed cards from MongoDB...", flush=True)
    db_pointed_cursor = cards_collection.find(
        {"genesys_points": {"$gt": 0}},
        {"_id": 1, "card_id": 1, "name.en": 1, "genesys_points": 1},
    )
    db_pointed = {}
    for doc in db_pointed_cursor:
        card_id = doc.get("card_id")
        if card_id is None:
            continue
        try:
            card_id = int(card_id)
        except (ValueError, TypeError):
            pass
        db_pointed[card_id] = {
            "_id": doc["_id"],
            "name_en": doc.get("name", {}).get("en", ""),
            "current_points": doc.get("genesys_points", 0),
        }
    print(f"Found {len(db_pointed)} pointed cards in MongoDB", flush=True)

    updates = []
    changes = []

    for card_id, info in db_pointed.items():
        if card_id not in nexus_points:
            changes.append((info["name_en"], info["current_points"], 0))
            updates.append(UpdateOne({"_id": info["_id"]}, {"$set": {"genesys_points": 0}}))

    for card_id, points in nexus_points.items():
        if card_id in db_pointed:
            changes.append((db_pointed[card_id]["name_en"], db_pointed[card_id]["current_points"], points))
            if db_pointed[card_id]["current_points"] != points:
                updates.append(UpdateOne({"_id": db_pointed[card_id]["_id"]}, {"$set": {"genesys_points": points}}))
        else:
            found = _find_card_by_card_id(cards_collection, card_id)
            if found:
                name = found.get("name", {}).get("en", str(card_id))
                changes.append((name, 0, points))
                updates.append(UpdateOne({"_id": found["_id"]}, {"$set": {"genesys_points": points}}))
            else:
                print(f"  WARNING: {card_id} not found in database, cannot update points", flush=True)

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
