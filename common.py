import os
import json
import shutil
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
import requests
import boto3
from PIL import Image
from pymongo import MongoClient, ReplaceOne
import pymongo
from bs4 import BeautifulSoup
import urllib3
from urllib3.exceptions import ReadTimeoutError

BASE_DIR = Path(__file__).parent.resolve()
DATASET_URL = "https://dawnbrandbots.github.io/yaml-yugi/cards.json"
SETS_URL = "https://yugioh-proxy.santirivera92.workers.dev/cardsets"
ADVANCED_BANLIST_URL = "https://raw.githubusercontent.com/SantiagoRivera92/TimeWizard/refs/heads/main/banlists/2026-05-11.json"

MONGO_URI = os.getenv("MONGO_URI")
S3_API_URL = os.getenv("S3_API_URL")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")

FORBIDDEN = "Forbidden"
LIMITED = "Limited"
SEMILIMITED = "Semi-Limited"
UNLIMITED = "Unlimited"
UNRELEASED = "Unreleased"

REGULAR_DM_ID = 46986414
ARKANA_DM_ID = 36996508
POLY_ID = 24094653
FUSION_ID = 27847700

RARITY_EQUIVALENCES = {
    "10000 Secret Rare": "10000ScR", "Collector's Rare": "CR", "Common": "C",
    "Duel Terminal Normal Parallel Rare": "DNPR", "Duel Terminal Normal Rare Parallel Rare": "DNRPR",
    "Duel Terminal Rare Parallel Rare": "DRPR", "Duel Terminal Super Parallel Rare": "DSPR",
    "Duel Terminal Ultra Parallel Rare": "DUPR", "Extra Secret Rare": "EScR", "Ghost Rare": "GR",
    "Ghost/Gold Rare": "GGR", "Gold Rare": "GUR", "Gold Secret Rare": "GScR",
    "Mosaic Rare": "MSR", "Normal Parallel Rare": "NPR", "Platinum Rare": "PlR",
    "Platinum Secret Rare": "PlScR", "Premium Gold Rare": "PGR", "Prismatic Secret Rare": "PScR",
    "Quarter Century Secret Rare": "QCScR", "Rare": "R", "Secret Rare": "ScR",
    "Shatterfoil Rare": "SHR", "Short Print": "SP", "Starfoil Rare": "SFR",
    "Starlight Rare": "StR", "Super Parallel Rare": "SPR", "Super Rare": "SR",
    "Super Short Print": "SSP", "Ultimate Rare": "UtR", "Ultra Parallel Rare": "UPR",
    "Ultra Rare": "UR", "Ultra Rare (Pharaoh's Rare)": "URPR", "Ultra Secret Rare": "UScR",
}

REVERSED_RARITY_EQUIVALENCES = {v: k for k, v in RARITY_EQUIVALENCES.items()}

SET_EQUIVALENCES = {
    "Premium Pack (TCG)": "Premium Pack", "Premium Pack 2 (TCG)": "Premium Pack 2",
    "Yu-Gi-Oh! Championship Series 2011 Prize Card": "Yu-Gi-Oh! Championship Series Prize Cards",
    "Ghosts From the Past (set)": "Ghosts From the Past", "Duel Terminal 5a": "Duel Terminal 5",
    "Duel Terminal 5b": "Duel Terminal 5", "Duel Terminal 6a": "Duel Terminal 6",
    "Duel Terminal 6b": "Duel Terminal 6", "Duel Terminal 7a": "Duel Terminal 7",
    "Duel Terminal 7b": "Duel Terminal 7", "Magic Ruler": "Spell Ruler",
    "Structure Deck: Marik (TCG)": "Structure Deck: Marik",
    "Yu-Gi-Oh! Advent Calendar (2018)": "Yu-Gi-Oh! Advent Calendar",
    "Yu-Gi-Oh! Advent Calendar (2019)": "Yu-Gi-Oh! Advent Calendar",
    "Dark Revelation Volume 2": "Dark Revelation 2", "2015 Mega-Tin": "2015 Mega-Tins",
    "Shadow of Infinity Sneak Peek participation card": "Shadow of Infinity Sneak Peek Participation Card",
    "Yu-Gi-Oh! 5D's Duel Transer Promotional Cards": "Yu-Gi-Oh! 5D's Duel Transer promotional cards",
    "Maximum Crisis Special Edition": "Maximum Crisis: Special Edition",
    "Yu-Gi-Oh! 5D's volume 8 promotional card": "Yu-Gi-Oh! 5D's Volume 8 promotional card",
    "2002 Booster Pack Tins": "Booster Pack Collectors Tins 2002",
}

ADD_NORMAL_IF_MISSING = [
    "Alexandrite Dragon", "Bujin Hiruko", "Bunilla", "Dragon Horn Hunter", "Dragong",
    "Dragonpit Magician", "Dragonpulse Magician", "Dragoons of Draconia", "Evilswarm Heliotrope",
    "Gem-Knight Crystal", "Gem-Knight Lapis", "Gem-Knight Sapphire", "Gem-Knight Tourmaline",
    "Hieratic Seal of the Sun Dragon Overlord", "Igknight Cavalier", "Igknight Crusader",
    "Igknight Gallant", "Igknight Margrave", "Igknight Paladin", "Igknight Squire",
    "Igknight Templar", "Igknight Veteran", "Master Pendulum, the Dracoslayer", "Megalosmasher X",
    "Metaphys Armed Dragon", "Mist Valley Watcher", "Noble Knight Artorigus", "Phantasm Spiral Dragon",
    "Phantom Gryphon", "Qliphort Monolith", "Risebell the Summoner", "Sea Dragoons of Draconia",
    "Shovel Crusher", "Sky Dragoons of Draconia", "Trance the Magic Swordsman", "Unicycular",
    "Vector Pendulum, the Dracoverlord", "Wattaildragon", "White Duston", "X-Saber Anu Piranha"
]

ADD_EFFECT_IF_MISSING = [
    "Alien Hypno", "Ally of Justice Cyclone Creator", "Aquarian Alessa", "Arcane Apprentice",
    "Armor Breaker", "Attack Gainer", "Blackwing - Hillen the Tengu-wind", "Blackwing - Jin the Rain Shadow",
    "Burning Beast", "Buster Blaster", "Buten", "Changer Synchron", "Cherry Inmato",
    "Chthonian Emperor Dragon", "Comrade Swordsman of Landstar", "Counselor Lily", "Dark Dust Spirit",
    "Dark Tinker", "Dawnbreak Gardna", "Delta Flyer", "Des Dendle", "Doitsu",
    "Dragunity Aklys", "Dread Dragon", "Eccentric Boy", "Egotistical Ape", "Elephun",
    "Emissary from Pandemonium", "Evocator Chevalier", "Fenghuang", "Flamvell Archer",
    "Freezing Beast", "Frequency Magician", "Fushi No Tori", "Future Samurai", "Gem-Knight Amber",
    "Gem-Knight Iolite", "Gem-Knight Sardonyx", "Gemini Lancer", "Gemini Soldier",
    "Genex Ally Chemistrer", "Genex Ally Remote", "Gishki Emilia", "Gishki Natalia",
    "Goggle Golem", "Grasschopper", "Great Long Nose", "Gundari", "Gusto Egul",
    "Gusto Falco", "Gusto Gulldo", "Gusto Squirro", "Hieratic Seal of the Dragon King",
    "Inaba White Rabbit", "Infernity Avenger", "Infernity Beetle", "Infinity Dark",
    "Influence Dragon", "Izanami", "Jurrac Aeolo", "Jurrac Brachis", "Jurrac Dino",
    "Jurrac Gallim", "Jurrac Monoloph", "Jutte Fighter", "Kagemusha of the Six Samurai",
    "Karakuri Barrel mdl 96 \"Shinkuro\"", "Karakuri Komachi mdl 224 \"Ninishi\"",
    "Karakuri Strategist mdl 248 \"Nishipachi\"", "Karakuri Watchdog mdl 313 \"Saizan\"",
    "King Pyron", "Kiryu", "Koitsu", "Laval Coatl", "Laval Forest Sprite", "Laval Lakeside Lady",
    "Lucky Pied Piper", "Maharaghi", "Malefic Parallel Gear", "Mental Seeker", "Mist Valley Windmaster",
    "Morphtronic Lantron", "Morphtronic Scopen", "Mystic Macrocarpa Seed", "Nettles", "Nikitama",
    "Phantom Dragonray Bronto", "Pitch-Dark Dragon", "Protective Soul Ailin", "Psychic Commander",
    "Quick-Span Knight", "R-Genex Oracle", "R-Genex Overseer", "Rasetsu", "Reese the Ice Mistress",
    "Reptilianne Viper", "Rose, Warrior of Revenge", "Royal Swamp Eel", "Scrap Beast", "Scrap Mind Reader",
    "Scrap Soldier", "Scrap Worm", "Second Goblin", "Shadow Delver", "Shiba-Warrior Taro", "Shien's Squire",
    "Sinister Sprocket", "Snyffus", "Soaring Eagle Above the Searing Land", "Spirit of the Six Samurai",
    "Sunny Pixie", "Susa Soldier", "Sword Master", "Symphonic Warrior Basses", "Symphonic Warrior Drumss",
    "Symphonic Warrior Piaano", "Synchro Magnet", "The Fabled Rubyruda", "Top Runner", "Torapart",
    "Trigon", "Trust Guardian", "Tuned Magician", "Turbo Rocket", "Uni-Horned Familiar", "Vylon Cube",
    "Vylon Pentachloro", "Vylon Prism", "Vylon Sphere", "Vylon Stella", "Vylon Tesseract", "Vylon Tetra",
    "Wattberyx", "Wattbetta", "Wattfox", "Wattkiwi", "X-Saber Palomuro", "X-Saber Pashuul", "Yaksha",
    "Yamata Dragon", "Yamato-no-Kami", "Metallizing Parasite - Soltite", "Mind Master", "Minerva, Lightsworn Maiden"
]

CARD_ID_EQUIVALENCES = [
    ["Obelisk the Tormentor", 10000000], ["The Winged Dragon of Ra", 10000010],
    ["Slifer the Sky Dragon", 10000020], ["The Winged Dragon of Ra - Sphere Mode", 10000080],
    ["The Winged Dragon of Ra - Immortal Phoenix", 10000090],
]

NAME_ALIASES = {
    "Amazoness Archer": ["Amazon Archer"],
    "Armityle the Chaos Phantasm": ["Armityle the Chaos Phantom"],
    "B.E.S. Big Core": ["Big Core"],
    "Big Shield Gardna": ["Big Shield Guardna"],
    "Black Dragon's Chick": ["Red-Eyes B. Chick"],
    "Black Skull Dragon": ["B. Skull Dragon"],
    "Cemetary Bomb": ["Cemetery Bomb"],
    "Cipher Soldier": ["Kinetic Soldier"],
    "Corruption Cell \"A\"": ["Corruption Cell A"],
    "Counter Gem": ["Crystal Counter"],
    "Damage Vaccine \u03a9 MAX": ["Damage Vaccine Omega MAX"],
    "Dark Assailant": ["Dark Assassin"],
    "Dark Scorpion - Cliff the Trap Remover": ["Cliff the Trap Remover"],
    "Darkfall": ["Dark Trap Hole"],
    "Darklord Marie": ["Marie the Fallen One"],
    "Darklord Nurse Reficule": ["Nurse Reficule the Fallen One"],
    "Destruction Dragon": ["Destruction Dragon - LC06-EN003"],
    "Dragon Revival Rhapsody": ["Dragon Revival Rhapsody - LC06-EN004"],
    "Earthbound Immortal Revival": ["Earthbound Revival"],
    "Evil Twin Ki-sikil Deal": ["EvilTwin Ki-sikil Deal"],
    "Falchion\u03b2": ["Falchion Beta"],
    "Fiendish Engine \u03a9": ["Fiendish Engine Omega"],
    "Flying Kamakiri #1": ["Flying Kamakiri 1"],
    "Giltia the D. Knight - Soul Spear": ["Giltia the D. Knight Soul Spear"],
    "Goddess of Sweet Revenge": ["Goddess of Sweet Revenge - LC06-EN001"],
    "Hidden Spellbook": ["Hidden Book of Spell"],
    "Hundred Eyes Dragon": ["Hundred-Eyes Dragon"],
    "Interplanetary Invader \"A\"": ["Interplanetary Invader 'A'"],
    "Kaiser Glider - Golden Burst": ["Kaiser Glider Golden Burst"],
    "Kuwagata \u03b1": ["Kuwagata Alpha", "Kuwagata"],
    "Live Twin Lil-la Sweet": ["LiveTwin Lil-la Sweet"],
    "Magicians Unite": ["Magician's Unite"],
    "Malefic Red-Eyes Black Dragon": ["Malefic Red-Eyes B. Dragon"],
    "Meteor Black Dragon": ["Meteor B. Dragon"],
    "Mini-Guts": ["Mini Guts"],
    "Mystical Elf - White Lightning": ["Mystical Elf White Lightning"],
    "Red-Eyes Black Dragon": ["Red-Eyes B. Dragon"],
    "Roar of the Earthbound Immortal": ["Roar of the Earthbound"],
    "Sephylon, the Ultimate Timelord": ["Sephylon, the Ultimate Time Lord"],
    "Silent Graveyard": ["Forbidden Graveyard"],
    "Sky Scout": ["Harpie's Brother"],
    "Slime Toad": ["Frog The Jam"],
    "Spell Reactor\uff65RE": ["Spell Reactor - RE"],
    "Spellbook Organization": ["Pigeonholing Books of Spell"],
    "Summon Reactor\uff65SK": ["Summon Reactor - SK"],
    "Supernatural Regeneration": ["Metaphysical Regeneration"],
    "Synch Blast Wave": ["Synchro Blast Wave"],
    "Synch Realm": ["Synchronized Realm"],
    "The King of D.": ["The King of D. - LC06-EN002"],
    "Token Feastevil": ["Token: Feastevil"],
    "Trap Reactor\uff65Y FI": ["Trap Reactor - Y FI"],
    "Vampire Baby": ["Red-Moon Baby"],
    "Vampiric Koala": ["Vampire Koala"],
    "Vampiric Orchis": ["Vampire Orchis"],
    "Wattkid": ["Oscillo Hero #2"],
}

WRONG_ALT_ARTS = [
    "MAMA-EN075", "SDMY-EN042", "LART-EN027", "DUDE-EN003",
    "SDWD-EN001", "SDWD-EN002", "SDWD-EN003", "SDCR-EN003",
    "YGLD-ENC41", "MFC-105", "LEDD-ENC32", "LEDD-ENC29",
    "LCKC-EN046", "DL12-EN008", "LDS1-EN068", "LEDD-ENC25",
    "LEDD-ENC01", "LOB-EN001", "LC01-EN004", "MAMA-EN104",
    "LDS2-EN001", "LCKC-EN001", "LDK2-ENK01", "SDBE-EN001",
    "DL09-EN001", "RP01-EN001", "LOB-EN005", "YGLD-ENC09",
    "YGLD-ENB02", "YGLD-ENB02", "MAMA-EN105", "LDS1-EN001",
    "LDK2-ENJ01", "LEDD-ENA01", "RP01-EN003", "LOB-003",
    "LDS3-EN082", "YGLD-ENB03", "YGLD-ENC10", "LC01-EN005",
]

RARITY_COLLECTION_RARITY_EQUIVALENCES = {
    "Collector's Rare": "Prismatic Collector's Rare",
    "Ultimate Rare": "Prismatic Ultimate Rare",
}

HIDDEN_ARSENAL_CHAPTER_1_EQUIVALENCES = {
    "Duel Terminal Normal Parallel Rare": "Duel Terminal Technology Common",
    "Duel Terminal Ultra Parallel Rare": "Duel Terminal Technology Ultra Rare",
}

SECRET_RARE_PROMO_EQUIVALENCES = {
    "Prismatic Secret Rare": "Secret Rare",
}

SECRET_RARE_PROMO_SETS = ["PCK", "DDS", "PCY", "DOR", "WC4", "TSC", "ROD"]

PROMOS = {"21CC-EN001"}

RARITY_ORDER = {
    "Common": 1, "C": 1, "Rare": 2, "R": 2, "Super Rare": 3, "SR": 3,
    "Ultra Rare": 4, "UR": 4, "Secret Rare": 5, "ScR": 5,
    "Prismatic Secret Rare": 6, "PScR": 6, "Platinum Secret Rare": 7, "PlScR": 7,
    "Ultimate Rare": 8, "UtR": 8, "Collector's Rare": 9, "CR": 9,
    "Quarter Century Secret Rare": 10, "QCScR": 10, "Starlight Rare": 11, "StR": 11,
    "Ghost Rare": 12, "GR": 12, "Duel Terminal Normal Parallel Rare": 13, "DNPR": 13,
    "Duel Terminal Normal Rare Parallel Rare": 14, "DNRPR": 14,
    "Duel Terminal Rare Parallel Rare": 15, "DRPR": 15,
    "Duel Terminal Super Parallel Rare": 16, "DSPR": 16,
    "Duel Terminal Ultra Parallel Rare": 17, "DUPR": 17,
    "Duel Terminal Secret Parallel Rare": 18, "DScPR": 18,
    "10000 Secret Rare": 19, "10000ScR": 19, "Extra Secret Rare": 20, "EScR": 20,
    "Ghost/Gold Rare": 21, "GGR": 21, "Gold Rare": 22, "GUR": 22,
    "Gold Secret Rare": 23, "GScR": 23, "Mosaic Rare": 24, "MSR": 24,
    "Normal Parallel Rare": 25, "NPR": 25, "Platinum Rare": 26, "PlR": 26,
    "Premium Gold Rare": 27, "PGR": 27, "Shatterfoil Rare": 28, "SHR": 28,
    "Short Print": 29, "SP": 29, "Starfoil Rare": 30, "SFR": 30,
    "Super Parallel Rare": 31, "SPR": 31, "Super Short Print": 32, "SSP": 32,
    "Ultra Parallel Rare": 33, "UPR": 33, "Ultra Rare (Pharaoh's Rare)": 34,
    "Ultra Secret Rare": 35, "UScR": 35, "Normal Rare": 36,
    "20th Secret Rare": 37, "Secret Rare (Special Blue Version)": 38,
    "Secret Rare (Special Red Version)": 39, "Ultra Rare (Special Purple Version)": 40,
    "Ultra Rare (Special Blue Version)": 41, "Ultra Rare (Special Red Version)": 42,
    "Holographic Rare": 43, "Rare Parallel Rare": 44, "Secret Parallel Rare": 45,
    "Holographic Parallel Rare": 46, "Extra Secret Parallel Rare": 47,
    "Kaiba Corporation Common": 48, "Kaiba Corporation Rare": 49,
    "Kaiba Corporation Super Rare": 50, "UtRPR": 50, "Kaiba Corporation Ultra Rare": 51,
    "UtRScR": 51, "Kaiba Corporation Secret Rare": 52, "Millennium Rare": 53, "MR": 53,
    "Millennium Super Rare": 54, "MScR": 54, "Millennium Ultra Rare": 55, "MUR": 55,
    "Millennium Secret Rare": 56, "MScR": 56, "Millennium Gold Rare": 57, "MGR": 57,
    "Grand Master Rare": 58, "GMR": 58,
}

EXCLUDED_SETS_TIME_WIZARD = ["DT01", "DT02", "DT03", "DT04", "DT05", "DT06", "DT07"]
EXCLUDED_FROM_DIAGNOSTIC_ERRORS = ["SDWD", "YGLD", "SGX3"]

SUPPORTED_LANGUAGES = ["en", "de", "es", "fr", "it", "pt", "ja", "ko"]
TCG_LANGUAGES = ["en", "de", "es", "fr", "it", "pt"]

OUTPUT_PATH = BASE_DIR / "data/output/cards.json"
OUTPUT_ERRORS_PATH = BASE_DIR / "data/output/errors.json"
FORMATS_DATA_PATH = BASE_DIR / "data/input/formats.json"
CARD_SETS_DATA_PATH = BASE_DIR / "data/input/sets_without_a_date.json"
ARTS_PATH = BASE_DIR / "data/input/arts.json"
ARTWORKS_PATH = BASE_DIR / "data/input/artworks.json"
MD_CARDS_PATH = BASE_DIR / "data/input/md_cards.json"
DL_CARDS_PATH = BASE_DIR / "data/input/dl_cards.json"
BANLIST_FOLDER = BASE_DIR / "data/formats/"
MD_BANLIST_FOLDER = BASE_DIR / "data/formats_md/"
CACHE_DIR = BASE_DIR / "mediawiki_cache"
GALLERY_TOUCHED_PATH = CACHE_DIR / "_touched.json"
MEDIAWIKI_TEST_PATH = BASE_DIR / "mediawiki_test"

# CardPrintImages collection name
CARD_PRINT_IMAGES_COLLECTION = "CardPrintImages"


# --- Gallery Touched Tracking ---
def load_touched_map():
    try:
        with open(GALLERY_TOUCHED_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_touched_map(touched_map):
    if not touched_map:
        return
    GALLERY_TOUCHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GALLERY_TOUCHED_PATH, "w") as f:
        json.dump(touched_map, f, indent=2)


def batch_get_gallery_touched(card_names):
    result = {}
    headers = {'User-Agent': 'Excavate by DiamondDude/1.0 (https://www.excavate.top)'}
    for i in range(0, len(card_names), 50):
        batch = card_names[i:i+50]
        titles = "|".join(f"Card Gallery:{n}" for n in batch)
        params = {
            "action": "query",
            "prop": "info",
            "titles": titles,
            "format": "json",
            "formatversion": "2",
        }
        for attempt in range(3):
            try:
                response = requests.get(API_URL, params=params, headers=headers, timeout=60)
                if response.status_code in (520, 429, 502, 503):
                    time.sleep(5)
                    continue
                data = response.json()
                for page in data.get("query", {}).get("pages", []):
                    title = page.get("title", "")
                    if title.startswith("Card Gallery:"):
                        name = title[len("Card Gallery:"):]
                        result[name] = page.get("touched", "")
                break
            except Exception:
                time.sleep(5)
                continue
    print(f"  Checked {len(result)} gallery pages for modifications")
    return result


class StepTimer:
    def __init__(self, step_name):
        self.step_name = step_name
        self.start = None

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        elapsed = time.time() - self.start
        print(f"  [TIMING] {self.step_name}: {elapsed:.3f}s")


# --- File / API Utilities ---

def load_json_file(file_path, encoding="utf-8"):
    try:
        with open(file_path, "r", encoding=encoding) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: File not found {file_path}. Returning empty.")
        return [] if ".json" in str(file_path) else {}
    except json.JSONDecodeError:
        print(f"Warning: Could not decode JSON from {file_path}. Returning empty.")
        return [] if ".json" in str(file_path) else {}


def save_json_file(data, file_path, encoding="utf-8", indent=4):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding=encoding) as f:
        json.dump(data, f, indent=indent)


def fetch_json_from_url(url, timeout=30):
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        raise SystemExit(f"Failed to fetch critical data from {url}") from e


def fetch_genesys_points_json(timeout=30):
    try:
        body = {"resultsPerPage": 10000, "currentPage": 1}
        url = "https://registration.yugioh-card.com/genesys/CardListSearch/PointsList"
        response = requests.post(url, data=body, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        results = data["Result"]["Results"]
        return {item["Name"]: item["Points"] for item in results}
    except requests.exceptions.RequestException as e:
        print("Error fetching Genesys points")
        raise SystemExit("Failed to fetch critical data") from e


def fetch_currently_pointed_cards(mongo_databases):
    try:
        pointed_cards = mongo_databases["spellbook_dev_db"].find(
            {"genesys_points": {"$gt": 0}}, {"name.en": 1, "genesys_points": 1}
        )
        return [card["name"]["en"] for card in pointed_cards]
    except Exception as e:
        print("Error fetching currently pointed cards from MongoDB, returning empty list")
        return []


# --- Card Utilities ---

def get_earliest_tcg_date(card_data):
    if "sets" not in card_data or "en" not in card_data["sets"] or len(card_data["sets"]["en"]) == 0:
        return None
    english_sets = card_data["sets"]["en"]
    earliest_tcg_date = "9999-12-31"
    for printing in english_sets:
        if printing.get("set_number", "")[:4] in EXCLUDED_SETS_TIME_WIZARD:
            continue
        date = printing.get("print_date")
        if date and date < earliest_tcg_date:
            earliest_tcg_date = date
    return earliest_tcg_date if earliest_tcg_date != "9999-12-31" else None


def get_localized_value(card_data, field_name):
    values = {}
    if field_name in card_data:
        for language in SUPPORTED_LANGUAGES:
            if language in card_data[field_name]:
                values[language] = card_data[field_name][language]
    return values


# --- S3 Utilities ---

def _get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_API_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
    )


def list_s3_files_in_webp():
    s3 = _get_s3_client()
    prefix = "webp/"
    files = set()
    continuation_token = None
    while True:
        kwargs = {"Bucket": S3_BUCKET_NAME, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = s3.list_objects_v2(**kwargs)
        for obj in response.get("Contents", []):
            files.add(obj["Key"])
        if not response.get("IsTruncated"):
            break
        continuation_token = response["NextContinuationToken"]
    print(f"Found {len(files)} files in S3 /webp/")
    return files


def list_s3_art_files_in_webp():
    s3 = _get_s3_client()
    prefix = "art/"
    files = set()
    continuation_token = None
    while True:
        kwargs = {"Bucket": S3_BUCKET_NAME, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = s3.list_objects_v2(**kwargs)
        for obj in response.get("Contents", []):
            files.add(obj["Key"])
        if not response.get("IsTruncated"):
            break
        continuation_token = response["NextContinuationToken"]
    print(f"Found {len(files)} files in S3 /art/")
    return files


def download_transform_and_upload_image(image_url, output_path):
    webp_output_path = None
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)
        img = Image.open(output_path)
        webp_output_path = output_path.with_suffix(".webp")
        img.save(webp_output_path, "webp")
        uploaded_name = webp_output_path.name
        uploaded_name = re.sub(r'%[0-9A-Fa-f]{2}', '', uploaded_name)
        print(f"Uploading to S3 webp/{uploaded_name}")
        s3 = _get_s3_client()
        s3.upload_file(str(webp_output_path), S3_BUCKET_NAME, f"webp/{uploaded_name}")
        return True
    except Exception as e:
        print(f"Error processing image {image_url}: {e}")
        return False
    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        if webp_output_path and os.path.exists(webp_output_path):
            try:
                os.remove(webp_output_path)
            except Exception:
                pass


def download_transform_and_upload_card_image(card_data, output_path):
    webp_output_path = None
    try:
        password = card_data.get("card_id")
        if password is None:
            print(f"Error: {card_data['name']['en']} does not contain 'card_id'. Cannot download image.")
            return False
        url = f"https://yugioh-proxy.santirivera92.workers.dev/art/{password}"
        print(f"Downloading art for {card_data['name']['en']}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)
        img = Image.open(output_path)
        webp_output_path = output_path.with_suffix(".webp")
        img.save(webp_output_path, "webp")
        s3 = _get_s3_client()
        s3.upload_file(str(webp_output_path), S3_BUCKET_NAME, f"art/{webp_output_path.name}")
        return True
    except Exception as e:
        print(f"Error processing art for {card_data['name']['en']}: {e}")
        return False
    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        if webp_output_path and os.path.exists(webp_output_path):
            try:
                os.remove(webp_output_path)
            except Exception:
                pass


def s3_url_from_raw(raw_image_url):
    image_url_no_ext = raw_image_url.split("/")[-1].rsplit('.', 1)[0]
    image_file_as_webp = "webp/" + image_url_no_ext + ".webp"
    image_file_as_webp = re.sub(r'%[0-9A-Fa-f]{2}', '', image_file_as_webp)
    return "https://r2.spellbook.life/" + image_file_as_webp, image_file_as_webp


# --- MongoDB Utilities ---

def get_mongo_client():
    return MongoClient(MONGO_URI)


def get_mongo_databases():
    client = get_mongo_client()
    return {
        "spellbook_dev_db": client["Cards"].Cards,
        "spellbook_prod_db": client["Cards"].Cards,
    }


def get_card_print_images_collection(client=None):
    if client is None:
        client = get_mongo_client()
    return client["Cards"][CARD_PRINT_IMAGES_COLLECTION]


def get_image_lookup_from_collection(collection):
    lookup = {}
    for doc in collection.find({}, {"_id": 0}):
        if "set_number" not in doc:
            continue
        key = (doc["set_number"], doc["set_name"], doc["rarity"], doc["art_id"])
        lookup[key] = doc["image_url"]
    print(f"Loaded {len(lookup)} image URL mappings from CardPrintImages")
    return lookup


def upsert_card_print_image(collection, set_number, set_name, rarity, art_id, suffix, image_url):
    doc_id = f"{set_number}|{set_name}|{rarity}|{art_id}"
    collection.replace_one(
        {"_id": doc_id},
        {
            "_id": doc_id,
            "set_number": set_number,
            "set_name": set_name,
            "rarity": rarity,
            "art_id": art_id,
            "suffix": suffix or "",
            "image_url": image_url,
            "updated_at": datetime.utcnow().isoformat(),
        },
        upsert=True,
    )


# --- Gallery Utilities (from mediawiki_api.py) ---

API_URL = "https://yugipedia.com/api.php"

GALLERY_SECTIONS = {
    "card-gallery--EN": "Worldwide English",
    "card-gallery--NA": "North American English",
    "card-gallery--EU": "European English",
    "card-gallery--AU": "Australian English",
    "card-gallery--FR": "French",
    "card-gallery--FC": "French-Canadian",
    "card-gallery--DE": "German",
    "card-gallery--IT": "Italian",
    "card-gallery--PT": "Portuguese",
    "card-gallery--SP": "Spanish",
    "card-gallery--JP": "Japanese",
    "card-gallery--KO": "Korean",
    "card-gallery--AE": "Asian-English",
    "card-gallery--SC": "Simplified Chinese",
}

LANGUAGE_EQUIVALENCES = {
    "English": "en", "French": "fr", "German": "de", "Italian": "it",
    "Portuguese": "pt", "Spanish": "es", "Japanese": "ja", "Korean": "ko",
    "Asian-English": "ae", "Simplified Chinese": "sc",
}

LANG_CODE_FROM_SECTION = {
    "French": "fr", "French-Canadian": "fr", "German": "de",
    "Italian": "it", "Portuguese": "pt", "Spanish": "es",
    "Japanese": "ja", "Korean": "ko", "Asian-English": "ae",
    "Simplified Chinese": "sc",
}

GALLERY_SET_EQUIVALENCES = {
    **SET_EQUIVALENCES,
    "Shadow of Infinity Sneak Peek participation card": "Shadow of Infinity Sneak Peek Participation Card",
    "Yu-Gi-Oh! 5D's Duel Transer Promotional Cards": "Yu-Gi-Oh! 5D's Duel Transer promotional cards",
    "Maximum Crisis Special Edition": "Maximum Crisis: Special Edition",
    "Yu-Gi-Oh! 5D's volume 8 promotional card": "Yu-Gi-Oh! 5D's Volume 8 promotional card",
    "2002 Booster Pack Tins": "Booster Pack Collectors Tins 2002",
}


def _transform_image_url(url):
    if "//thumb" not in url:
        return url
    url = url.replace("//thumb/", "//")
    last_slash_index = url.rfind("/")
    if last_slash_index != -1:
        url = url[:last_slash_index]
    return url


def get_card_gallery(card_name, use_cache=True):
    sanitized_card_name = "".join(c for c in card_name if c.isalnum() or c in (" ", "-", "_"))
    cache_file_path = os.path.join(CACHE_DIR, f"{sanitized_card_name}.json")
    if os.path.exists(cache_file_path):
        cache_age = time.time() - os.path.getmtime(cache_file_path)
        if cache_age < 1209600 and use_cache:
            with open(cache_file_path, 'r', encoding="utf-8") as cache_file:
                try:
                    cached = json.load(cache_file)
                    # Support both old format (data directly) and new (data + _touched)
                    if "data" in cached:
                        return cached["data"], cached.get("_touched", "")
                    return cached, ""
                except json.decoder.JSONDecodeError:
                    print("Faulty cache, downloading again")

    card_name = card_name.replace("#", "").replace("<", "").replace(">", "")
    gallery_title = f"Card Gallery:{card_name}"
    params = {
        "action": "parse",
        "page": gallery_title,
        "format": "json",
        "prop": "sections|text",
        "formatversion": "2",
    }
    headers = {'User-Agent': 'Excavate by DiamondDude/1.0 (https://www.excavate.top)'}

    for _ in range(20):
        try:
            response = requests.get(API_URL, params=params, headers=headers, timeout=120)
            if response.status_code in (520, 429, 403, 502, 503):
                time.sleep(10)
                continue
            try:
                data = response.json()
            except (requests.exceptions.JSONDecodeError, Exception):
                time.sleep(10)
                continue

            if "error" in data:
                if "(card)" not in card_name:
                    result, _ = get_card_gallery(card_name=f"{card_name} (card)", use_cache=use_cache)
                    return result, ""
                return None, ""

            if "parse" not in data:
                print(f"No gallery found for {card_name}")
                return None, ""

            result = {}
            content = data["parse"]["text"]
            soup = BeautifulSoup(content, "html.parser")

            for gallery_id, section_name in GALLERY_SECTIONS.items():
                gallery_div = soup.find("div", id=gallery_id)
                if not gallery_div:
                    continue
                if section_name in ["Worldwide English", "North American English", "European English", "Australian English"]:
                    if "en" not in result:
                        result["en"] = []
                    for li in gallery_div.find_all("li", class_="gallerybox"):
                        print_info = _extract_print_info(li)
                        if print_info:
                            result["en"].extend(print_info)
                else:
                    lang_code = LANG_CODE_FROM_SECTION.get(section_name)
                    if lang_code:
                        if lang_code not in result:
                            result[lang_code] = []
                        for li in gallery_div.find_all("li", class_="gallerybox"):
                            print_info = _extract_print_info(li)
                            if print_info:
                                result[lang_code].extend(print_info)

            tables = soup.find_all("table", class_="card-galleries")
            for table in tables:
                language_text = table.find("th").get_text()
                language_code = "en"
                for language, code in LANGUAGE_EQUIVALENCES.items():
                    if language in language_text:
                        language_code = code
                        break
                gallery_boxes = table.find_all("ul", class_="gallery mw-gallery-traditional")
                for box in gallery_boxes:
                    items = box.find_all("li", class_="gallerybox")
                    for item in items:
                        image = item.find("img")
                        links = item.find("div", class_="gallerytext").find_all("a")
                        if len(links) < 4:
                            continue
                        for link in links:
                            title = link.get("title")
                            if title and "Giant Card" in title:
                                continue
                        if "Case Topper" in links[2].get_text():
                            continue
                        if links[1].get_text() == "Official Proxy":
                            continue
                        print_info = {}
                        if image and "src" in image.attrs:
                            print_info["image_url"] = _transform_image_url(image["src"])
                        else:
                            print_info["image_url"] = None
                        print_info["set_number"] = links[0].get_text()
                        print_info["rarity"] = links[1].get_text()
                        print_info["edition"] = links[2].get_text()
                        print_info["set_name"] = GALLERY_SET_EQUIVALENCES.get(links[3].get("title"), links[3].get("title"))
                        print_info_array = [print_info]
                        if len(links) > 4:
                            print_info_array.append({
                                "set_number": links[0].get_text(),
                                "rarity": links[1].get_text(),
                                "edition": links[2].get_text(),
                                "set_name": GALLERY_SET_EQUIVALENCES.get(links[4].get("title"), links[4].get("title")),
                                "image_url": _transform_image_url(image["src"]),
                            })
                        if language_code not in result:
                            result[language_code] = []
                        for pi in print_info_array:
                            result[language_code].append(pi)

            touched = data.get("parse", {}).get("touched", "")
            if result:
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(cache_file_path, 'w', encoding="utf-8") as cf:
                    json.dump({"_touched": touched, "data": result}, cf)
            return result, touched

        except (TimeoutError, requests.exceptions.ReadTimeout, urllib3.exceptions.ProtocolError,
                requests.exceptions.ConnectionError, ReadTimeoutError, Exception):
            time.sleep(10)

    print(f"Failed to fetch gallery for {card_name} after multiple attempts.")
    return None, ""


def _extract_print_info(li):
    print_info = {}
    gallery_text = li.find("div", class_="gallerytext")
    if not gallery_text:
        return None
    links = gallery_text.find_all("a")
    img = li.find("img")
    if img and "src" in img.attrs:
        print_info["image_url"] = _transform_image_url(img["src"])
    else:
        print_info["image_url"] = None
    if len(links) == 3 and ("-JP" in links[0].get("title") or "-SC" in links[0].get("title")):
        if links[1].get_text() == "Official Proxy":
            return None
        print_info["set_number"] = links[0].get_text()
        print_info["rarity"] = links[1].get_text()
        print_info["set_name"] = GALLERY_SET_EQUIVALENCES.get(links[2].get("title"), links[2].get("title"))
        print_info["edition"] = None
        return [print_info]
    if len(links) < 4:
        return None
    for link in links:
        title = link.get("title")
        if title and "Giant Card" in title:
            return None
    print_info["set_number"] = links[0].get_text()
    print_info["rarity"] = links[1].get_text()
    print_info["edition"] = links[2].get_text()
    print_info["set_name"] = GALLERY_SET_EQUIVALENCES.get(links[3].get("title"), links[3].get("title"))
    if len(links) > 4:
        pi2 = {
            "set_number": links[0].get_text(),
            "rarity": links[1].get_text(),
            "edition": links[2].get_text(),
            "set_name": GALLERY_SET_EQUIVALENCES.get(links[4].get("title"), links[4].get("title")),
            "image_url": print_info["image_url"],
        }
        return [print_info, pi2]
    return [print_info]


# --- Card Processing Functions ---

def transform_basic_card_info(raw_card, transformed_card):
    if "konami_id" not in raw_card or raw_card["konami_id"] is None:
        return False
    card_name_en = transformed_card["name"]["en"]
    transformed_card["konami_id"] = raw_card["konami_id"]
    transformed_card["_id"] = raw_card["konami_id"]
    if "password" in raw_card and raw_card["password"] is not None:
        transformed_card["card_id"] = raw_card["password"]
    else:
        for name, c_id in CARD_ID_EQUIVALENCES:
            if card_name_en == name:
                transformed_card["card_id"] = c_id
                break
    transformed_card["card_type"] = raw_card.get("card_type", None)
    if "monster_type_line" in raw_card:
        transformed_card["typeline"] = raw_card["monster_type_line"]
    elif "property" in raw_card:
        transformed_card["typeline"] = raw_card["property"]
    if card_name_en in ADD_NORMAL_IF_MISSING and "Normal" not in transformed_card.get("typeline", ""):
        transformed_card["typeline"] = transformed_card["typeline"] + " / Normal"
    if card_name_en in ADD_EFFECT_IF_MISSING and "Effect" not in transformed_card.get("typeline", ""):
        transformed_card["typeline"] = transformed_card["typeline"] + " / Effect"
    if "atk" in raw_card:
        transformed_card["atk"] = -1 if raw_card["atk"] == "?" else raw_card["atk"]
    if "def" in raw_card:
        transformed_card["def"] = -1 if raw_card["def"] == "?" else raw_card["def"]
    if "level" in raw_card:
        transformed_card["level"] = raw_card["level"]
    elif "rank" in raw_card:
        transformed_card["level"] = raw_card["rank"]
    if "link_arrows" in raw_card:
        transformed_card["link_arrows"] = raw_card["link_arrows"]
        transformed_card["level"] = len(raw_card["link_arrows"])
    if "pendulum_scale" in raw_card:
        transformed_card["scale"] = raw_card["pendulum_scale"]
    if "series" in raw_card:
        transformed_card["archetypes"] = raw_card["series"]
    if "attribute" in raw_card:
        transformed_card["attribute"] = raw_card["attribute"]
    return True


def process_card_sets(raw_card_sets, card_name_en, loaded_data):
    transformed_sets_by_lang = {lang: [] for lang in SUPPORTED_LANGUAGES}
    artworks_map = loaded_data.get("artworks_map", {})
    raw_sets_by_name = loaded_data.get("raw_sets_by_name", {})
    sets_without_date_by_name = loaded_data.get("sets_without_date_by_name", {})

    for lang in SUPPORTED_LANGUAGES:
        if lang not in raw_card_sets:
            continue
        for printing in raw_card_sets[lang]:
            if not ("rarities" in printing and printing["rarities"] and
                    "set_number" in printing and printing["set_number"] and
                    "?" not in printing["set_number"] and
                    "Stainless Steel" not in printing.get("set_name", "")):
                continue
            for rarity in printing["rarities"]:
                set_number = printing["set_number"]
                set_code_parts = set_number.split("-")
                if len(set_code_parts) < 2:
                    continue
                set_code = set_code_parts[0]
                code_number_suffix = set_code_parts[1]
                code_number = code_number_suffix[-3:]
                set_name = printing["set_name"]
                print_date = "9999-12-31"
                if set_name in raw_sets_by_name:
                    print_date = raw_sets_by_name[set_name].get("tcg_date", "9999-12-31")
                if print_date == "9999-12-31" and set_name in sets_without_date_by_name:
                    print_date = sets_without_date_by_name[set_name].get("date", "9999-12-31")

                if card_name_en in artworks_map:
                    card_artworks_data = artworks_map[card_name_en]
                    artwork_matched = False
                    for art_detail in card_artworks_data:
                        art_detail_prints = art_detail.get("prints", [])
                        correct_print_without_lang = any(
                            set_code in p and code_number in p for p in art_detail_prints
                        )
                        if set_number in art_detail_prints or correct_print_without_lang:
                            artwork_matched = True
                            add_this_art = False
                            if "rarities" in art_detail:
                                if RARITY_EQUIVALENCES.get(rarity) in art_detail["rarities"]:
                                    add_this_art = True
                            else:
                                add_this_art = True
                            if add_this_art:
                                suffixes = art_detail.get("suffix", [""] * 5)
                                art_ids = art_detail.get("art_ids", [])
                                for i, art_id_val in enumerate(art_ids):
                                    transformed_sets_by_lang[lang].append({
                                        "set_number": set_number, "set_name": set_name,
                                        "print_date": print_date, "rarity": rarity,
                                        "art_id": art_id_val, "suffix": suffixes[i] if suffixes else "",
                                        "image_url": None,
                                    })
                    if not artwork_matched:
                        transformed_sets_by_lang[lang].append({
                            "set_number": set_number, "set_name": set_name,
                            "print_date": print_date, "rarity": rarity,
                            "art_id": 1, "suffix": "", "image_url": None,
                        })
                else:
                    transformed_sets_by_lang[lang].append({
                        "set_number": set_number, "set_name": set_name,
                        "print_date": print_date, "rarity": rarity,
                        "art_id": 1, "suffix": "", "image_url": None,
                    })

    final_sets = {}
    for lang, prints in transformed_sets_by_lang.items():
        if prints:
            valid_prints = []
            errors = []
            for p in prints:
                if p is None or not p.get("print_date") or not p.get("rarity"):
                    continue
                rarity = p["rarity"]
                if rarity not in RARITY_ORDER:
                    errors.append(f"Unknown rarity found: '{rarity}' for language {lang}")
                valid_prints.append(p)
            if errors:
                raise ValueError(errors)
            final_sets[lang] = sorted(
                valid_prints,
                key=lambda s: (s["print_date"], RARITY_ORDER[s["rarity"]]),
                reverse=True,
            )
    return final_sets


def update_card_statuses(transformed_card, loaded_data, raw_card_limit_reg):
    card_name_en = transformed_card.get('name', {}).get('en')
    if not card_name_en:
        return
    adv_banlist = loaded_data.get("advanced_banlist_data", {})
    formats_list = loaded_data.get("formats_list", [])
    filtered_sets_by_format = loaded_data.get("filtered_sets_by_format", {})

    transformed_card["status"] = {
        "Advanced": raw_card_limit_reg.get("tcg", UNRELEASED),
        "OCG": raw_card_limit_reg.get("ocg", UNRELEASED),
        "tw": {},
    }
    if transformed_card["status"]["Advanced"] == "Not yet released":
        transformed_card["status"]["Advanced"] = UNRELEASED
    if transformed_card["status"]["OCG"] == "Not yet released":
        transformed_card["status"]["OCG"] = UNRELEASED

    if card_name_en in adv_banlist.get("forbidden", []):
        transformed_card["status"]["Advanced"] = FORBIDDEN
    elif card_name_en in adv_banlist.get("limited", []):
        transformed_card["status"]["Advanced"] = LIMITED
    elif card_name_en in adv_banlist.get("semilimited", []):
        transformed_card["status"]["Advanced"] = SEMILIMITED
    else:
        transformed_card["status"]["Advanced"] = UNLIMITED

    for fmt in formats_list:
        fmt_name = fmt.get("name")
        if not fmt_name:
            continue
        status = UNRELEASED
        if card_name_en in fmt.get("forbidden", []):
            status = FORBIDDEN
        elif card_name_en in fmt.get("limited", []):
            status = LIMITED
        elif card_name_en in fmt.get("semilimited", []):
            status = SEMILIMITED
        elif card_name_en in fmt.get("unlimited", []):
            status = UNLIMITED
        else:
            if "en" in transformed_card.get("sets", {}):
                for printing in transformed_card["sets"]["en"]:
                    if printing.get("set_number", "")[:4] in EXCLUDED_SETS_TIME_WIZARD:
                        continue
                    normalized_print_set_name = SET_EQUIVALENCES.get(printing.get("set_name", ""), printing.get("set_name", "")).lower()
                    if fmt_name in filtered_sets_by_format:
                        for legal_set in filtered_sets_by_format[fmt_name]:
                            normalized_legal_set_name = SET_EQUIVALENCES.get(legal_set.get("set_name", ""), legal_set.get("set_name", "")).lower()
                            if normalized_print_set_name == normalized_legal_set_name:
                                status = UNLIMITED
                                break
                    if status == UNLIMITED:
                        break
        transformed_card["status"]["tw"][fmt_name] = status

    transformed_card["status"]["Common Charity"] = UNRELEASED
    common_rarities = ["Common", "Short Print", "Super Short Print"]
    for lang in TCG_LANGUAGES:
        if lang in transformed_card.get("sets", {}):
            for printing in transformed_card["sets"][lang]:
                if printing.get("rarity") in common_rarities:
                    transformed_card["status"]["Common Charity"] = transformed_card["status"]["Advanced"]
                    break
            if transformed_card["status"]["Common Charity"] != UNRELEASED:
                break


def add_videogame_data(transformed_card, loaded_data):
    card_name_en = transformed_card.get('name', {}).get('en')
    if not card_name_en:
        return
    md_cards_list = loaded_data.get("md_cards_list", [])
    dl_cards_list = loaded_data.get("dl_cards_list", [])

    main_image_file = None
    if "en" in transformed_card.get("sets", {}):
        priority_rarities = ["Common", "Rare", "Super Rare", "Ultra Rare", "Secret Rare"]
        for p in transformed_card["sets"]["en"]:
            if p.get("image_url") and p.get("rarity") in priority_rarities and p.get("art_id") == 1 and "LART" not in p.get("set_number"):
                main_image_file = p["image_url"].split("/")[-1]
                break
        if not main_image_file:
            for p in transformed_card["sets"]["en"]:
                if p.get("image_url"):
                    main_image_file = p["image_url"].split("/")[-1]
                    break
    if not main_image_file:
        priority_rarities = ["Common", "Rare", "Super Rare", "Ultra Rare", "Secret Rare"]
        for _, prints in transformed_card.get("sets", {}).items():
            for p in prints:
                if p.get("rarity") in priority_rarities and p.get("art_id") == 1 and p.get("image_url"):
                    main_image_file = p["image_url"].split("/")[-1]
                    break
        if not main_image_file:
            for _, prints in transformed_card.get("sets", {}).items():
                for p in prints:
                    if p.get("image_url"):
                        main_image_file = p["image_url"].split("/")[-1]
                        break

    if main_image_file:
        transformed_card["image_url"] = main_image_file

    md_card_data = next((c for c in md_cards_list if c.get("name", "").lower() == card_name_en.lower()), None)
    if md_card_data:
        transformed_card["status"]["MD"] = md_card_data.get("status", UNRELEASED)
        transformed_card["md_prints"] = md_card_data.get("prints", [])
        transformed_card["md_release"] = md_card_data.get("release")
        if main_image_file:
            for md_print in transformed_card["md_prints"]:
                md_print["image_url"] = main_image_file
    else:
        print("No card data found for MD:", card_name_en)
        transformed_card["status"]["MD"] = UNRELEASED
        transformed_card["md_release"] = None

    transformed_card["tcg_release"] = get_earliest_tcg_date(transformed_card)

    dl_card_data = next((c for c in dl_cards_list if c.get("name", "").lower() == card_name_en.lower()), None)
    if dl_card_data:
        transformed_card["status"]["DL"] = dl_card_data.get("status", UNRELEASED)
        transformed_card["dl_prints"] = dl_card_data.get("prints", [])
        if main_image_file:
            for dl_print in transformed_card["dl_prints"]:
                dl_print["image_url"] = main_image_file
    else:
        transformed_card["status"]["DL"] = UNRELEASED


def add_banlist_history(transformed_card, loaded_data):
    card_name_en = transformed_card.get('name', {}).get('en')
    if not card_name_en:
        return
    tcg_banlists_map = loaded_data.get("tcg_banlists_map", {})
    transformed_card["banlist_data"] = {}

    earliest_tcg_print_date = None
    if "en" in transformed_card.get("sets", {}):
        for printing in transformed_card["sets"]["en"]:
            if printing.get("set_number", "")[:4] in EXCLUDED_SETS_TIME_WIZARD:
                continue
            current_print_date = printing.get("print_date")
            if current_print_date and (earliest_tcg_print_date is None or current_print_date < earliest_tcg_print_date):
                earliest_tcg_print_date = current_print_date

    if earliest_tcg_print_date is None:
        for lang_sets in transformed_card.get("sets", {}).values():
            for printing in lang_sets:
                if printing.get("set_number", "")[:4] in EXCLUDED_SETS_TIME_WIZARD:
                    continue
                current_print_date = printing.get("print_date")
                if current_print_date and (earliest_tcg_print_date is None or current_print_date < earliest_tcg_print_date):
                    earliest_tcg_print_date = current_print_date

    for banlist_date_str, banlist_content in tcg_banlists_map.items():
        status_code = -1
        if card_name_en in banlist_content.get("forbidden", set()):
            status_code = 0
        elif card_name_en in banlist_content.get("limited", set()):
            status_code = 1
        elif card_name_en in banlist_content.get("semilimited", set()):
            status_code = 2
        elif card_name_en in banlist_content.get("unlimited", set()):
            status_code = 3
        else:
            if earliest_tcg_print_date and earliest_tcg_print_date <= banlist_date_str:
                status_code = 3
        transformed_card["banlist_data"][banlist_date_str] = status_code


def add_md_banlist_history(transformed_card, loaded_data):
    card_name_en = transformed_card.get('name', {}).get('en')
    if not card_name_en:
        return
    md_banlists_map = loaded_data.get("md_banlists_map", {})
    transformed_card["md_banlist_data"] = {}
    md_release_date = transformed_card.get("md_release")
    if not md_banlists_map:
        return
    for banlist_date_str, banlist_content in md_banlists_map.items():
        status_code = -1
        if card_name_en in banlist_content.get("forbidden", set()):
            status_code = 0
        elif card_name_en in banlist_content.get("limited", set()):
            status_code = 1
        elif card_name_en in banlist_content.get("semilimited", set()):
            status_code = 2
        else:
            if md_release_date and md_release_date <= banlist_date_str:
                status_code = 3
        transformed_card["md_banlist_data"][banlist_date_str] = status_code


def assign_genesys_points(transformed_card, genesys_points):
    card_name_en = transformed_card.get('name', {}).get('en')
    typeline = transformed_card.get('typeline', "")
    if not card_name_en:
        return
    if card_name_en in genesys_points:
        transformed_card["genesys_points"] = genesys_points[card_name_en]
    elif "Link" in typeline or "Pendulum" in typeline:
        transformed_card["genesys_points"] = -1
    else:
        transformed_card["genesys_points"] = 0


# --- Image Matching / Assignment ---

def find_image_for_printing(printing, gallery_info, lang="en"):
    set_name = SET_EQUIVALENCES.get(printing["set_name"], printing["set_name"])
    set_number = printing["set_number"]
    rarity_full = printing["rarity"]
    rarity_code = RARITY_EQUIVALENCES.get(rarity_full, rarity_full)
    suffix = printing.get("suffix", "")

    for gallery_item in gallery_info.get(lang, []):
        g_set_name = gallery_item.get("set_name")
        g_set_number = gallery_item.get("set_number")
        g_rarity = gallery_item.get("rarity")
        g_image_url = gallery_item.get("image_url")
        if not g_image_url:
            continue
        if g_set_name == set_name and g_set_number == set_number and g_rarity == rarity_code:
            if suffix and suffix in g_image_url:
                return g_image_url
            if not suffix:
                return g_image_url

    if rarity_full in ["Common", "Short Print", "Super Short Print"]:
        for gallery_item in gallery_info.get(lang, []):
            g_set_name = gallery_item.get("set_name")
            g_set_number = gallery_item.get("set_number")
            g_rarity = gallery_item.get("rarity")
            g_image_url = gallery_item.get("image_url")
            if g_set_name == set_name and g_set_number == set_number and g_rarity in ["C", "SP", "SSP"] and g_image_url:
                return g_image_url
    return None


def apply_image_urls_from_lookup(transformed_card, image_lookup):
    for lang in SUPPORTED_LANGUAGES:
        if lang not in transformed_card.get("sets", {}):
            continue
        for printing in transformed_card["sets"][lang]:
            set_name_norm = SET_EQUIVALENCES.get(printing["set_name"], printing["set_name"])
            key = (printing["set_number"], set_name_norm, printing["rarity"], printing.get("art_id", 1))
            if key in image_lookup:
                printing["image_url"] = image_lookup[key]


def assign_image_urls_and_upload(transformed_card, gallery_info, s3_webp_files, card_print_images_collection):
    files_to_download = []
    new_lookup_entries = []

    if not gallery_info:
        return

    # For each lang
    for lang in SUPPORTED_LANGUAGES:
        if lang not in transformed_card.get("sets", {}) or lang not in gallery_info:
            continue
        for printing in transformed_card["sets"][lang]:
            original_set_name = printing["set_name"]
            set_name = SET_EQUIVALENCES.get(original_set_name, original_set_name)
            if set_name != original_set_name:
                printing["set_name"] = set_name
            raw_url = find_image_for_printing(printing, gallery_info, lang)
            if raw_url:
                s3_url, s3_key = s3_url_from_raw(raw_url)
                printing["image_url"] = s3_url
                if s3_key not in s3_webp_files:
                    files_to_download.append((raw_url, s3_url, s3_key))
                new_lookup_entries.append(
                    (printing["set_number"], set_name, printing["rarity"],
                     printing.get("art_id", 1), printing.get("suffix", ""), s3_url)
                )

    # Fallback for Common/SP/SSP with no match
    for lang in SUPPORTED_LANGUAGES:
        if lang not in transformed_card.get("sets", {}) or lang not in gallery_info:
            continue
        for printing in transformed_card["sets"][lang]:
            if printing.get("image_url") is not None:
                continue
            if printing["rarity"] not in ["Common", "Short Print", "Super Short Print"]:
                continue
            set_name = SET_EQUIVALENCES.get(printing["set_name"], printing["set_name"])
            set_number = printing["set_number"]
            for gallery_item in gallery_info.get(lang, []):
                if (gallery_item.get("set_name") == set_name and
                    gallery_item.get("set_number") == set_number and
                    gallery_item.get("rarity") in ["C", "SP", "SSP"] and
                    gallery_item.get("image_url")):
                    raw_url = gallery_item["image_url"]
                    s3_url, s3_key = s3_url_from_raw(raw_url)
                    printing["image_url"] = s3_url
                    if s3_key not in s3_webp_files:
                        files_to_download.append((raw_url, s3_url, s3_key))
                    break

    # Download missing images
    if files_to_download:
        print(f"Downloading {len(files_to_download)} new images for {transformed_card.get('name', {}).get('en', 'Unknown')}")
        for raw_url, s3_url, s3_key in files_to_download:
            output_path = Path(BASE_DIR, "temp_images", raw_url.split("/")[-1])
            if download_transform_and_upload_image(raw_url, output_path):
                s3_webp_files.add(s3_key)

    # Update CardPrintImages
    if card_print_images_collection is not None and new_lookup_entries:
        for set_number, set_name, rarity, art_id, suffix, image_url in new_lookup_entries:
            upsert_card_print_image(card_print_images_collection, set_number, set_name, rarity, art_id, suffix, image_url)

    # Assign file field
    for lang_prints_key in list(transformed_card.get("sets", {}).keys()):
        for printing in transformed_card["sets"][lang_prints_key]:
            if printing.get("image_url"):
                printing["file"] = printing["image_url"].split("/")[-1]


# --- Initial Data Loading ---

def load_initial_data(mongo_databases=None, update_videogame_data=False):
    data = {}
    print("Loading initial data...")

    with StepTimer("load_artworks_map"):
        data["artworks_map"] = load_json_file(ARTS_PATH)
    with StepTimer("load_artwork_urls_map"):
        data["artwork_urls_map"] = load_json_file(ARTWORKS_PATH)
    with StepTimer("load_formats_list"):
        data["formats_list"] = load_json_file(FORMATS_DATA_PATH)
    with StepTimer("load_sets_without_date_list"):
        data["sets_without_date_list"] = load_json_file(CARD_SETS_DATA_PATH)
        data["sets_without_date_by_name"] = {s["name"]: s for s in data["sets_without_date_list"]}

    with StepTimer("load_tcg_banlists"):
        data["tcg_banlists_map"] = {}
        for file_path in BANLIST_FOLDER.glob("*.json"):
            banlist = load_json_file(file_path)
            data["tcg_banlists_map"][file_path.stem] = {
                "forbidden": set(banlist.get("forbidden", [])),
                "limited": set(banlist.get("limited", [])),
                "semilimited": set(banlist.get("semilimited", [])),
                "unlimited": set(banlist.get("unlimited", [])),
            }

    with StepTimer("load_md_banlists"):
        data["md_banlists_map"] = {}
        if MD_BANLIST_FOLDER.exists():
            for file_path in MD_BANLIST_FOLDER.glob("*.json"):
                banlist = load_json_file(file_path)
                data["md_banlists_map"][file_path.stem] = {
                    "forbidden": set(banlist.get("forbidden", [])),
                    "limited": set(banlist.get("limited", [])),
                    "semilimited": set(banlist.get("semilimited", [])),
                    "unlimited": set(banlist.get("unlimited", [])),
                }
        else:
            print(f"Warning: MD banlist folder not found at {MD_BANLIST_FOLDER}.")

    if update_videogame_data:
        print("Dumping DL and MD cards...")
        from meta_dump import dump_all
        dump_all()

    with StepTimer("load_md_cards_list"):
        data["md_cards_list"] = load_json_file(MD_CARDS_PATH)
    with StepTimer("load_dl_cards_list"):
        data["dl_cards_list"] = load_json_file(DL_CARDS_PATH)

    print("Fetching data from APIs...")
    with StepTimer("fetch_raw_sets_list"):
        data["raw_sets_list"] = fetch_json_from_url(SETS_URL)
        data["raw_sets_by_name"] = {s["set_name"]: s for s in data["raw_sets_list"]}
    with StepTimer("fetch_advanced_banlist"):
        data["advanced_banlist_data"] = fetch_json_from_url(ADVANCED_BANLIST_URL)
    with StepTimer("fetch_genesys_points"):
        data["genesys_points"] = fetch_genesys_points_json()
    if mongo_databases:
        with StepTimer("fetch_currently_pointed"):
            data["currently_pointed_cards"] = fetch_currently_pointed_cards(mongo_databases)

    with StepTimer("build_filtered_sets"):
        data["filtered_sets_by_format"] = {
            fmt["name"]: [
                s for s in data["raw_sets_list"]
                if "tcg_date" in s and s["tcg_date"] and
                    datetime.strptime(s["tcg_date"], "%Y-%m-%d") < datetime.strptime(fmt["date"], "%Y-%m-%d")
            ]
            for fmt in data["formats_list"] if "date" in fmt and fmt["date"]
        }
    print("Initial data loaded.")
    return data


# --- DM/Polymerization merge logic ---

def merge_dm_and_arkana(processed_cards):
    regular_dm = next((c for c in processed_cards if c.get("card_id") == REGULAR_DM_ID), None)
    arkana_dm = next((c for c in processed_cards if c.get("card_id") == ARKANA_DM_ID), None)
    if regular_dm and arkana_dm:
        new_list = [c for c in processed_cards if c.get("card_id") not in [REGULAR_DM_ID, ARKANA_DM_ID]]
        for lang in SUPPORTED_LANGUAGES:
            if lang in arkana_dm.get("sets", {}):
                regular_dm_sets = regular_dm.setdefault("sets", {}).setdefault(lang, [])
                regular_dm_sets.extend(arkana_dm["sets"][lang])
                regular_dm_sets.sort(key=lambda s: s["print_date"], reverse=True)
                seen = set()
                unique = []
                for p in regular_dm_sets:
                    key = (p.get("set_number"), p.get("rarity"), p.get("art_id"))
                    if key not in seen:
                        seen.add(key)
                        unique.append(p)
                regular_dm["sets"][lang] = unique
        new_list.append(regular_dm)
        return new_list
    return processed_cards


def merge_poly_and_fusion(processed_cards):
    poly = next((c for c in processed_cards if c.get("card_id") == POLY_ID), None)
    fusion = next((c for c in processed_cards if c.get("card_id") == FUSION_ID), None)
    if poly and fusion:
        new_list = [c for c in processed_cards if c.get("card_id") not in [POLY_ID, FUSION_ID]]
        for lang in SUPPORTED_LANGUAGES:
            if lang in fusion.get("sets", {}):
                poly_sets = poly["sets"][lang] + fusion["sets"][lang]
                poly_sets.sort(key=lambda s: s["print_date"], reverse=True)
                seen = set()
                unique = []
                for p in poly_sets:
                    key = (p.get("set_number"), p.get("rarity"), p.get("art_id"))
                    if key not in seen:
                        seen.add(key)
                        unique.append(p)
                poly["sets"][lang] = unique
        new_list.append(poly)
        return new_list
    return processed_cards


def finalize_card(card):
    if card.get("card_id") == ARKANA_DM_ID:
        # Assign file field
        for lang_prints_key in list(card.get("sets", {}).keys()):
            for printing in card["sets"][lang_prints_key]:
                if printing.get("image_url"):
                    printing["file"] = printing["image_url"].split("/")[-1]
