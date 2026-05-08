import os
import json
import sys
from pathlib import Path
from pymongo import MongoClient, ReplaceOne

BASE_DIR = Path(__file__).parent.resolve()
FORMATS_PATH = BASE_DIR / "data/input/formats.json"
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    print("Error: MONGO_URI environment variable is not set.")
    sys.exit(1)


def main():
    with open(FORMATS_PATH, "r", encoding="utf-8") as f:
        formats = json.load(f)

    if not isinstance(formats, list):
        print("Error: formats.json must contain a JSON array.")
        sys.exit(1)

    print(f"Loaded {len(formats)} formats from {FORMATS_PATH}")

    client = MongoClient(MONGO_URI)
    db = client["Cards"]
    collection = db["TimeWizardFormats"]

    ops = []
    for fmt in formats:
        name = fmt.get("name")
        if not name:
            print(f"Warning: skipping format without name: {fmt}")
            continue
        fmt["_id"] = name
        ops.append(ReplaceOne({"_id": name}, fmt, upsert=True))

    if ops:
        result = collection.bulk_write(ops, ordered=False)
        print(f"Upserted {result.upserted_count}, modified {result.modified_count}, matched {result.matched_count} documents")
    else:
        print("No formats to upsert.")

    client.close()
    print("Done.")


if __name__ == "__main__":
    main()
