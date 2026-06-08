import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import get_mongo_client, fetch_genesys_points_json, MONGO_URI
from pymongo import UpdateOne


def main():
    if not MONGO_URI:
        print("Error: MONGO_URI environment variable not set", flush=True)
        sys.exit(1)

    print("Connecting to MongoDB...", flush=True)
    client = get_mongo_client()
    cards_collection = client["Cards"].Cards

    print("Fetching Genesys points from Konami...", flush=True)
    genesys_points = fetch_genesys_points_json()
    konami_pointed = {name: points for name, points in genesys_points.items() if points > 0}
    print(f"Found {len(konami_pointed)} pointed cards in Konami data", flush=True)

    print("Fetching currently pointed cards from MongoDB...", flush=True)
    db_pointed_cursor = cards_collection.find(
        {"genesys_points": {"$gt": 0}},
        {"_id": 1, "name.en": 1, "genesys_points": 1},
    )
    db_pointed = {}
    for doc in db_pointed_cursor:
        name_en = doc.get("name", {}).get("en", "")
        if name_en:
            db_pointed[name_en] = {
                "konami_id": doc["_id"],
                "current_points": doc.get("genesys_points", 0),
            }
    print(f"Found {len(db_pointed)} pointed cards in MongoDB", flush=True)

    updates = []

    for name, info in db_pointed.items():
        if name not in konami_pointed:
            print(f"  {name}: {info['current_points']} → 0 (removed from Konami)", flush=True)
            updates.append(UpdateOne({"_id": info["konami_id"]}, {"$set": {"genesys_points": 0}}))

    for name, points in konami_pointed.items():
        if name in db_pointed:
            if db_pointed[name]["current_points"] != points:
                print(f"  {name}: {db_pointed[name]['current_points']} → {points}", flush=True)
                updates.append(UpdateOne({"_id": db_pointed[name]["konami_id"]}, {"$set": {"genesys_points": points}}))
        else:
            found = cards_collection.find_one({"name.en": name}, {"_id": 1})
            if found:
                print(f"  {name}: 0 → {points} (newly pointed)", flush=True)
                updates.append(UpdateOne({"_id": found["_id"]}, {"$set": {"genesys_points": points}}))
            else:
                print(f"  WARNING: {name} not found in database, cannot update points", flush=True)

    if updates:
        print(f"Applying {len(updates)} updates to MongoDB...", flush=True)
        result = cards_collection.bulk_write(updates, ordered=False)
        print(f"Matched: {result.matched_count}, Modified: {result.modified_count}", flush=True)
    else:
        print("No updates needed", flush=True)


if __name__ == "__main__":
    main()
