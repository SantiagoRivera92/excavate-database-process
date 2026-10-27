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


def _is_banned_type(typeline):
    """Genesys bans every Pendulum and Link monster, so they are stored with -1."""
    if not typeline:
        return False
    return "Pendulum" in typeline or "Link" in typeline


def _coerce_konami_id(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def _find_card_by_konami_id(collection, konami_id):
    for key in (konami_id, str(konami_id)):
        doc = collection.find_one(
            {"_id": key},
            {"_id": 1, "name.en": 1, "typeline": 1},
        )
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

    # Enforce the Genesys invariant up front: Pendulum and Link monsters are -1,
    # never 0 or positive. This repairs any stale data and makes every later
    # update idempotent for those cards.
    print("Backfilling Pendulum/Link cards to genesys_points=-1...", flush=True)
    backfill = cards_collection.update_many(
        {
            "typeline": {"$regex": "(Pendulum|Link)", "$options": "i"},
            "genesys_points": {"$ne": -1},
        },
        {"$set": {"genesys_points": -1}},
    )
    print(f"Backfilled {backfill.modified_count} card(s)", flush=True)

    print("Fetching Genesys points from yaml-yugi...", flush=True)
    yaml_yugi_points = fetch_genesys_points_from_yaml_yugi()
    print(f"Found {len(yaml_yugi_points)} pointed cards in yaml-yugi data", flush=True)

    manual_changes, manual_errors = parse_genesys_manual_updates()
    if manual_errors:
        print(
            f"WARNING: {len(manual_errors)} line(s) in the manual updates file could not be parsed",
            flush=True,
        )
    if manual_changes:
        print(
            f"Applying {len(manual_changes)} manual override(s) on top of upstream data...",
            flush=True,
        )
        manual_names = sorted({name for name, _, _ in manual_changes})
        name_to_cards = {}
        for doc in cards_collection.find(
            {"name.en": {"$in": manual_names}},
            {"_id": 1, "name.en": 1, "typeline": 1},
        ):
            name = doc.get("name", {}).get("en")
            if not name:
                continue
            name_to_cards.setdefault(name, []).append({
                "id": doc["_id"],
                "typeline": doc.get("typeline", ""),
            })
        applied = 0
        skipped_banned = 0
        missing = []
        for name, _old, new in manual_changes:
            cards = name_to_cards.get(name)
            if not cards:
                missing.append(name)
                continue
            for card in cards:
                card_key = _coerce_konami_id(card["id"])
                if _is_banned_type(card["typeline"]):
                    # A manual override must not reintroduce points for a card
                    # that Genesys bans outright.
                    skipped_banned += 1
                    yaml_yugi_points.pop(card_key, None)
                    continue
                if new > 0:
                    yaml_yugi_points[card_key] = new
                else:
                    yaml_yugi_points.pop(card_key, None)
                applied += 1
        print(
            f"Applied {applied} manual override(s) to {len(yaml_yugi_points)} pointed cards",
            flush=True,
        )
        if skipped_banned:
            print(
                f"WARNING: ignored {skipped_banned} manual override(s) for Pendulum/Link cards "
                f"(Genesys bans them)",
                flush=True,
            )
        if missing:
            print(
                f"WARNING: {len(missing)} manual override name(s) not found in database:",
                flush=True,
            )
            for name in missing:
                print(f"  {name}", flush=True)

    print("Fetching currently pointed cards from MongoDB...", flush=True)
    db_pointed_cursor = cards_collection.find(
        {"genesys_points": {"$gt": 0}},
        {"_id": 1, "name.en": 1, "genesys_points": 1, "typeline": 1},
    )
    db_pointed = {}
    for doc in db_pointed_cursor:
        konami_id = doc.get("_id")
        if konami_id is None:
            continue
        key = _coerce_konami_id(konami_id)
        db_pointed[key] = {
            "_id": doc["_id"],
            "name_en": doc.get("name", {}).get("en", ""),
            "current_points": doc.get("genesys_points", 0),
            "is_banned": _is_banned_type(doc.get("typeline", "")),
        }
    print(f"Found {len(db_pointed)} pointed cards in MongoDB", flush=True)

    updates = []
    changes = []

    # Any card that is still pointed in MongoDB but no longer in yaml-yugi
    # goes back to 0 — unless it's a banned Pendulum/Link, in which case -1.
    for konami_id, info in db_pointed.items():
        if info["is_banned"]:
            if info["current_points"] != -1:
                changes.append((info["name_en"], info["current_points"], -1))
                updates.append(
                    UpdateOne({"_id": info["_id"]}, {"$set": {"genesys_points": -1}})
                )
            continue
        if konami_id not in yaml_yugi_points:
            changes.append((info["name_en"], info["current_points"], 0))
            updates.append(
                UpdateOne({"_id": info["_id"]}, {"$set": {"genesys_points": 0}})
            )

    # Cards that are (still or newly) pointed in yaml-yugi.
    for konami_id, points in yaml_yugi_points.items():
        if konami_id in db_pointed:
            info = db_pointed[konami_id]
            if info["is_banned"]:
                # Handled above.
                continue
            changes.append((info["name_en"], info["current_points"], points))
            if info["current_points"] != points:
                updates.append(
                    UpdateOne({"_id": info["_id"]}, {"$set": {"genesys_points": points}})
                )
        else:
            found = _find_card_by_konami_id(cards_collection, konami_id)
            if not found:
                print(
                    f"  WARNING: {konami_id} not found in database, cannot update points",
                    flush=True,
                )
                continue
            name = found.get("name", {}).get("en", str(konami_id))
            if _is_banned_type(found.get("typeline", "")):
                # Backfill already set this to -1; nothing more to do.
                continue
            changes.append((name, 0, points))
            updates.append(
                UpdateOne({"_id": found["_id"]}, {"$set": {"genesys_points": points}})
            )

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