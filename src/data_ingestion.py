import os
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
import argparse
import requests
import boto3
from PIL import Image
from pymongo import MongoClient, ReplaceOne
from meta_dump import dump_all
from mediawiki_api import get_card_gallery
import pymongo
import re
from common import fetch_genesys_points_json, fetch_currently_pointed_cards, assign_genesys_points


def time_function(func):
    """Decorator to measure execution time of a function."""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"  [TIMING] {func.__name__}: {elapsed:.3f}s")
        return result
    return wrapper


class StepTimer:
    """Context manager to time code blocks."""
    def __init__(self, step_name):
        self.step_name = step_name
        self.start = None
    
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        elapsed = time.time() - self.start
        print(f"  [TIMING] {self.step_name}: {elapsed:.3f}s")

BASE_DIR = Path(__file__).resolve().parent.parent

# URLs
DATASET_URL = "https://dawnbrandbots.github.io/yaml-yugi/cards.json"
SETS_URL = "https://yugioh-proxy.santirivera92.workers.dev/cardsets"
ADVANCED_BANLIST_URL = "https://raw.githubusercontent.com/SantiagoRivera92/TimeWizard/refs/heads/main/banlists/2026-05-11.json"

# MongoDB URI
MONGO_URI = os.getenv("MONGO_URI")

# S3/Cloudflare R2
S3_API_URL = os.getenv("S3_API_URL")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")

# Script Behavior Flags
UPDATE_VIDEOGAME_DATA = False
USE_CACHE = False
DIAGNOSTIC_LOGGING = False
UPDATE_DATABASE = True
UPDATE_S3 = True
OVERWRITE_S3_FILES = False
UPDATE_ONLY_1_CARD = False
UPDATE_ONLY_GENESYS_POINTED_CARDS = False
CARD_TO_UPDATE = 0

# Banlist Status Constants
FORBIDDEN = "Forbidden"
LIMITED = "Limited"
SEMILIMITED = "Semi-Limited"
UNLIMITED = "Unlimited"
UNRELEASED = "Unreleased"

# Specific Card IDs
REGULAR_DM_ID = 46986414
ARKANA_DM_ID = 36996508
POLY_ID = 24094653
FUSION_ID = 27847700

# Rarity and Set Equivalences (Could be loaded from JSON/YAML for easier maintenance)
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
    "Genex Ally Chemistrer", "Genex Ally Remote", "Gishki Emilia","Gishki Natalia",
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
    "Quick-Span Knight", "R-Genex Oracle", "R-Genex Overseer", "Rasetsu","Reese the Ice Mistress",
    "Reptilianne Viper", "Rose, Warrior of Revenge", "Royal Swamp Eel", "Scrap Beast", "Scrap Mind Reader",
    "Scrap Soldier", "Scrap Worm", "Second Goblin", "Shadow Delver", "Shiba-Warrior Taro", "Shien's Squire",
    "Sinister Sprocket", "Snyffus","Soaring Eagle Above the Searing Land","Spirit of the Six Samurai",
    "Sunny Pixie", "Susa Soldier", "Sword Master", "Symphonic Warrior Basses", "Symphonic Warrior Drumss",
    "Symphonic Warrior Piaano", "Synchro Magnet", "The Fabled Rubyruda","Top Runner", "Torapart",
    "Trigon", "Trust Guardian", "Tuned Magician", "Turbo Rocket","Uni-Horned Familiar","Vylon Cube",
    "Vylon Pentachloro", "Vylon Prism", "Vylon Sphere", "Vylon Stella", "Vylon Tesseract", "Vylon Tetra",
    "Wattberyx", "Wattbetta", "Wattfox", "Wattkiwi", "X-Saber Palomuro", "X-Saber Pashuul", "Yaksha",
    "Yamata Dragon", "Yamato-no-Kami", "Metallizing Parasite - Soltite", "Mind Master", "Minerva, Lightsworn Maiden"
]

# Card ID Equivalences for cards without a password
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
    "Counter Gem":["Crystal Counter"],
    "Damage Vaccine Ω MAX":["Damage Vaccine Omega MAX"],
    "Dark Assailant": ["Dark Assassin"],
    "Dark Scorpion - Cliff the Trap Remover": ["Cliff the Trap Remover"],
    "Darkfall": ["Dark Trap Hole"],
    "Darklord Marie": ["Marie the Fallen One"],
    "Darklord Nurse Reficule": ["Nurse Reficule the Fallen One"],
    "Destruction Dragon": ["Destruction Dragon - LC06-EN003"],
    "Dragon Revival Rhapsody": ["Dragon Revival Rhapsody - LC06-EN004"],
    "Earthbound Immortal Revival": ["Earthbound Revival"],
    "Evil Twin Ki-sikil Deal": ["EvilTwin Ki-sikil Deal"],
    "Falchionβ": ["Falchion Beta"],
    "Fiendish Engine Ω": ["Fiendish Engine Omega"],
    "Flying Kamakiri #1": ["Flying Kamakiri 1"],
    "Giltia the D. Knight - Soul Spear": ["Giltia the D. Knight Soul Spear"],
    "Goddess of Sweet Revenge":["Goddess of Sweet Revenge - LC06-EN001"],
    "Hidden Spellbook": ["Hidden Book of Spell"],
    "Hundred Eyes Dragon": ["Hundred-Eyes Dragon"],
    "Interplanetary Invader \"A\"": ["Interplanetary Invader 'A'"],
    "Kaiser Glider - Golden Burst": ["Kaiser Glider Golden Burst"],
    "Kuwagata α": ["Kuwagata Alpha", "Kuwagata"],
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
    "Spell Reactor・RE": ["Spell Reactor - RE"],
    "Spellbook Organization": ["Pigeonholing Books of Spell"],
    "Summon Reactor・SK": ["Summon Reactor - SK"],
    "Supernatural Regeneration": ["Metaphysical Regeneration"],
    "Synch Blast Wave": ["Synchro Blast Wave"],
    "Synch Realm": ["Synchronized Realm"],
    "The King of D.": ["The King of D. - LC06-EN002"],
    "Token Feastevil": ["Token: Feastevil"],
    "Trap Reactor・Y FI": ["Trap Reactor - Y FI"],
    "Vampire Baby": ["Red-Moon Baby"],
    "Vampiric Koala": ["Vampire Koala"],
    "Vampiric Orchis": ["Vampire Orchis"],
    "Wattkid": ["Oscillo Hero #2"]
}

WRONG_ALT_ARTS = [
    "MAMA-EN075", "SDMY-EN042", "LART-EN027", "DUDE-EN003", 
    "SDWD-EN001", "SDWD-EN002", "SDWD-EN003", "SDCR-EN003", 
    "YGLD-ENC41", "MFC-105", "LEDD-ENC32", "LEDD-ENC29", 
    "LCKC-EN046", "DL12-EN008", "LDS1-EN068", "LEDD-ENC25",  
    "LEDD-ENC01", "LOB-EN001","LC01-EN004", "MAMA-EN104", 
    "LDS2-EN001","LCKC-EN001", "LDK2-ENK01", "SDBE-EN001", 
    "DL09-EN001", "RP01-EN001", "LOB-EN005", "YGLD-ENC09",
    "YGLD-ENB02", "YGLD-ENB02", "MAMA-EN105", "LDS1-EN001",
    "LDK2-ENJ01", "LEDD-ENA01", "RP01-EN003", "LOB-003",
    "LDS3-EN082", "YGLD-ENB03", "YGLD-ENC10", "LC01-EN005" ]

RARITY_COLLECTION_RARITY_EQUIVALENCES = {
    "Collector's Rare": "Prismatic Collector's Rare",
    "Ultimate Rare": "Prismatic Ultimate Rare",
}

HIDDEN_ARSENAL_CHAPTER_1_EQUIVALENCES = {
    "Duel Terminal Normal Parallel Rare": "Duel Terminal Technology Common",
    "Duel Terminal Ultra Parallel Rare": "Duel Terminal Technology Ultra Rare"
}

SECRET_RARE_PROMO_EQUIVALENCES = {
    "Prismatic Secret Rare": "Secret Rare"
}

SECRET_RARE_PROMO_SETS = [
    "PCK", "DDS", "PCY","DOR", "WC4", "TSC", "ROD"
]

PROMOS = {
    "21CC-EN001"
}

RARITY_ORDER = {
    "Common": 1,
    "C": 1,
    "Rare": 2,
    "R": 2,
    "Super Rare": 3,
    "SR": 3,
    "Ultra Rare": 4,
    "UR": 4,
    "Secret Rare": 5,
    "ScR": 5,
    "Prismatic Secret Rare": 6,
    "PScR": 6,
    "Platinum Secret Rare": 7,
    "PlScR": 7,
    "Ultimate Rare": 8,
    "UtR": 8,
    "Collector's Rare": 9,
    "CR": 9,
    "Quarter Century Secret Rare": 10,
    "QCScR": 10,
    "Starlight Rare": 11,
    "StR": 11,
    "Ghost Rare": 12,
    "GR": 12,
    "Duel Terminal Normal Parallel Rare": 13,
    "DNPR": 13,
    "Duel Terminal Normal Rare Parallel Rare": 14,
    "DNRPR": 14,
    "Duel Terminal Rare Parallel Rare": 15,
    "DRPR": 15,
    "Duel Terminal Super Parallel Rare": 16,
    "DSPR": 16,
    "Duel Terminal Ultra Parallel Rare": 17,
    "DUPR": 17,
    "Duel Terminal Secret Parallel Rare": 18,
    "DScPR": 18,
    "10000 Secret Rare": 19,
    "10000ScR": 19,
    "Extra Secret Rare": 20,
    "EScR": 20,
    "Ghost/Gold Rare": 21,
    "GGR": 21,
    "Gold Rare": 22,
    "GUR": 22,
    "Gold Secret Rare": 23,
    "GScR": 23,
    "Mosaic Rare": 24,
    "MSR": 24,
    "Normal Parallel Rare": 25,
    "NPR": 25,
    "Platinum Rare": 26,
    "PlR": 26,
    "Premium Gold Rare": 27,
    "PGR": 27,
    "Shatterfoil Rare": 28,
    "SHR": 28,
    "Short Print": 29,
    "SP": 29,
    "Starfoil Rare": 30,
    "SFR": 30,
    "Super Parallel Rare": 31,
    "SPR": 31,
    "Super Short Print": 32,
    "SSP": 32,
    "Ultra Parallel Rare": 33,
    "UPR": 33,
    "Ultra Rare (Pharaoh's Rare)": 34,
    "Ultra Secret Rare": 35,
    "UScR": 35,
    "Normal Rare": 36,
    "20th Secret Rare": 37,
    "Secret Rare (Special Blue Version)": 38,
    "Secret Rare (Special Red Version)": 39,
    "Ultra Rare (Special Purple Version)": 40,
    "Ultra Rare (Special Blue Version)": 41,
    "Ultra Rare (Special Red Version)": 42,
    "Holographic Rare": 43,
    "Rare Parallel Rare": 44,
    "Secret Parallel Rare": 45,
    "Holographic Parallel Rare": 46,
    "Extra Secret Parallel Rare": 47,
    "Kaiba Corporation Common": 48,
    "Kaiba Corporation Rare": 49,
    "Kaiba Corporation Super Rare": 50,
    "UtRPR": 50,
    "Kaiba Corporation Ultra Rare": 51,
    "UtRScR": 51,
    "Kaiba Corporation Secret Rare": 52,
    "Millennium Rare": 53,
    "MR": 53,
    "Millennium Super Rare": 54,
    "MScR": 54,
    "Millennium Ultra Rare": 55,
    "MUR": 55,
    "Millennium Secret Rare": 56,
    "MScR": 56,
    "Millennium Gold Rare": 57,
    "MGR": 57,
    "Grand Master Rare": 58,
    "GMR": 58,
}

# Time Wizard-excluded sets
EXCLUDED_SETS_TIME_WIZARD = ["DT01", "DT02", "DT03", "DT04", "DT05", "DT06", "DT07"]
EXCLUDED_FROM_DIAGNOSTIC_ERRORS = ["SDWD", "YGLD", "SGX3"]

SUPPORTED_LANGUAGES = ["en", "de", "es", "fr", "it", "pt", "ja", "ko"]
TCG_LANGUAGES = ["en", "de", "es", "fr", "it", "pt"]

OUTPUT_PATH = BASE_DIR / "data/output/cards.json"
OUTPUT_ERRORS_PATH = BASE_DIR / "data/output/errors.json"
FORMATS_DATA_PATH = BASE_DIR / "data/input/formats.json"
CARD_SETS_DATA_PATH = BASE_DIR / "data/input/sets_without_a_date.json"
ARTS_PATH = BASE_DIR / "data/input/arts.json"
GENESYS_POINTS = BASE_DIR / "data/input/genesys_points.json"
ARTWORKS_PATH = BASE_DIR / "data/input/artworks.json"
MD_CARDS_PATH = BASE_DIR / "data/input/md_cards.json"
DL_CARDS_PATH = BASE_DIR / "data/input/dl_cards.json"
BANLIST_FOLDER = BASE_DIR / "data/formats/"
MD_BANLIST_FOLDER = BASE_DIR / "data/formats_md/"
MEDIAWIKI_TEST_PATH = BASE_DIR / "mediawiki_test"

# --- Utility Functions ---
def load_json_file(file_path, encoding="utf-8"):
    """Loads a JSON file and returns its content."""
    try:
        with open(file_path, "r", encoding=encoding) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: File not found {file_path}. Returning empty dict/list.")
        return {} if "config" in str(file_path).lower() or "art" in str(file_path).lower() or "banlist" in str(file_path).lower() else []
    except json.JSONDecodeError:
        print(f"Warning: Could not decode JSON from {file_path}. Returning empty dict/list.")
        return {} if "config" in str(file_path).lower() or "art" in str(file_path).lower() or "banlist" in str(file_path).lower() else []


def save_json_file(data, file_path, encoding="utf-8", indent=4):
    """Saves data to a JSON file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding=encoding) as f:
        json.dump(data, f, indent=indent)


def fetch_json_from_url(url, timeout=10):
    """Fetches JSON data from a URL."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        # Depending on severity, you might want to raise the exception or exit
        raise SystemExit(f"Failed to fetch critical data from {url}") from e
    
def get_earliest_tcg_date(card_data):
    if "sets" not in card_data or "en" not in card_data["sets"] or len(card_data["sets"]["en"]) == 0: 
        return None
    english_sets = card_data["sets"]["en"]
    earliest_tcg_date = "9999-12-31"
    for printing in english_sets:
        if printing.get("set_number","")[:4] in EXCLUDED_SETS_TIME_WIZARD:
            continue
        date = printing.get("print_date")
        if date < earliest_tcg_date:
            earliest_tcg_date = date
    if earliest_tcg_date != "9999-12-31":
        return earliest_tcg_date
    return None
    

def get_localized_value(card_data, field_name):
    """Helper function to get supported language values for a field."""
    values = {}
    if field_name in card_data:
        for language in SUPPORTED_LANGUAGES:
            if language in card_data[field_name]:
                values[language] = card_data[field_name][language]
    return values

def list_s3_files_in_webp():
    """Returns a list of all files in the /webp folder in the S3 bucket."""
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_API_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
    )
    bucket = S3_BUCKET_NAME
    prefix = "webp/"
    files = []
    continuation_token = None

    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for obj in response.get("Contents", []):
            files.append(obj["Key"])
        print(f"Found {len(files)} files in S3 bucket {bucket}")
        if response.get("IsTruncated"):
            continuation_token = response["NextContinuationToken"]
            print("Continuing to next page of results...")
        else:
            break
    return files

def list_s3_art_files_in_webp():
    """Returns a list of all artwork files in the /webp folder in the S3 bucket."""
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_API_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
    )
    bucket = S3_BUCKET_NAME
    prefix = "art/"
    files = []
    continuation_token = None

    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for obj in response.get("Contents", []):
            files.append(obj["Key"])
        print(f"Found {len(files)} artwork files in S3 bucket {bucket}")
        if response.get("IsTruncated"):
            continuation_token = response["NextContinuationToken"]
            print("Continuing to next page of results...")
        else:
            break
    return files

def download_transform_and_upload_image(image_url, output_path):
    """Downloads an image, transforms it to WebP, and uploads it to S3."""
    if not UPDATE_S3:
        return False
    webp_output_path = None
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)

        # Transform to WebP
        img = Image.open(output_path)
        webp_output_path = output_path.with_suffix(".webp")
        img.save(webp_output_path, "webp")

        uploaded_name = webp_output_path.name
        uploaded_name = re.sub(r'%[0-9A-Fa-f]{2}', '', uploaded_name)
        
        print(f"Downloading {image_url} and uploading it to webp/{uploaded_name}")

        # Upload to S3
        s3 = boto3.client(
            "s3",
            endpoint_url=S3_API_URL,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
        )
        s3.upload_file(str(webp_output_path), S3_BUCKET_NAME, f"webp/{uploaded_name}")
        return True
    except Exception as e:
        print(f"Error processing image {image_url}: {e}")
        return False
    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception as e:
                print(f"Error deleting temporary image file {output_path}: {e}")
        if webp_output_path and os.path.exists(webp_output_path):
            try:
                os.remove(webp_output_path)
            except Exception as e:
                print(f"Error deleting temporary webp file {webp_output_path}: {e}")

def download_transform_and_upload_card_image(card_data, output_path):
    if not UPDATE_S3:
        return False
    webp_output_path = None
    try:
        password = card_data.get("card_id")
        if password is None:
            print(f"Error: {card_data['name']['en']} does not contain 'card_id'. Cannot download image.")
            return False
        url = f"https://yugioh-proxy.santirivera92.workers.dev/art/{password}"
        print(f"Downloading {url} for {card_data['name']['en']}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)

        img = Image.open(output_path)
        webp_output_path = output_path.with_suffix(".webp")
        img.save(webp_output_path, "webp")
        
        s3 = boto3.client(
            "s3",
            endpoint_url=S3_API_URL,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
        )
        s3.upload_file(str(webp_output_path), S3_BUCKET_NAME, f"art/{webp_output_path.name}")
        return True
    except Exception as e:
        print(f"Error processing art for {card_data['name']['en']}: {e}")
        return False
    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception as e:
                print(f"Error deleting temporary image file {output_path}: {e}")
        if webp_output_path and os.path.exists(webp_output_path):
            try:
                os.remove(webp_output_path)
            except Exception as e:
                print(f"Error deleting temporary webp file {webp_output_path}: {e}")


# --- Database Connection ---
def get_mongo_databases():
    """Initializes and returns MongoDB database connections."""
    try:
        mongo_client = MongoClient(MONGO_URI)
        return {
            "spellbook_dev_db": mongo_client["Cards"].Cards,
            "spellbook_prod_db": mongo_client["Cards"].Cards,
        }
    except KeyError as e:
        raise SystemExit(f"MongoDB URI not found in config: {e}") from e
    except Exception as e:
        raise SystemExit(f"Failed to connect to MongoDB: {e}") from e


# --- Data Loading ---
def load_initial_data(mongo_databases):
    """Loads all necessary initial data from files and APIs."""
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
        # Build lookup dictionaries for O(1) access
        data["sets_without_date_by_name"] = {s["name"]: s for s in data["sets_without_date_list"]}

    with StepTimer("load_tcg_banlists"):
        data["tcg_banlists_map"] = {}
        for file_path in BANLIST_FOLDER.glob("*.json"):
            banlist = load_json_file(file_path)
            # Convert lists to sets for O(1) lookups
            data["tcg_banlists_map"][file_path.stem] = {
                "forbidden": set(banlist.get("forbidden", [])),
                "limited": set(banlist.get("limited", [])),
                "semilimited": set(banlist.get("semilimited", [])),
                "unlimited": set(banlist.get("unlimited", []))
            }
    
    with StepTimer("load_md_banlists"):
        data["md_banlists_map"] = {} # New: For Master Duel banlists
        if MD_BANLIST_FOLDER.exists(): # Check if the folder exists
            for file_path in MD_BANLIST_FOLDER.glob("*.json"):
                banlist = load_json_file(file_path)
                # Convert lists to sets for O(1) lookups
                data["md_banlists_map"][file_path.stem] = {
                    "forbidden": set(banlist.get("forbidden", [])),
                    "limited": set(banlist.get("limited", [])),
                    "semilimited": set(banlist.get("semilimited", [])),
                    "unlimited": set(banlist.get("unlimited", []))
                }
        else:
            print(f"Warning: Master Duel banlist folder not found at {MD_BANLIST_FOLDER}. Skipping MD banlist loading.")

    if UPDATE_VIDEOGAME_DATA: # This flag is False in user's new script, so this block might not run
        print("Dumping DL and MD cards...")
        dump_all() 
    with StepTimer("load_md_cards_list"):
        data["md_cards_list"] = load_json_file(MD_CARDS_PATH) 
    with StepTimer("load_dl_cards_list"):
        data["dl_cards_list"] = load_json_file(DL_CARDS_PATH)

    print("Fetching data from APIs...")
    with StepTimer("fetch_raw_sets_list"):
        data["raw_sets_list"] = fetch_json_from_url(SETS_URL)
        # Build lookup dictionary for O(1) access by set_name
        data["raw_sets_by_name"] = {s["set_name"]: s for s in data["raw_sets_list"]}
    with StepTimer("fetch_advanced_banlist"):
        data["advanced_banlist_data"] = fetch_json_from_url(ADVANCED_BANLIST_URL)
    with StepTimer("fetch_genesys_points"):
        data["genesys_points"] = fetch_genesys_points_json()
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


def transform_basic_card_info(raw_card, transformed_card):
    """Transforms basic, non-localized card fields."""

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
        transformed_card["typeline"] = transformed_card["typeline"] +  " / Normal"
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
    """Processes and transforms card set information, including alternate artworks."""
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

                # O(1) lookup instead of O(n) scan
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
                                    if set_number == "RA04-EN106":
                                        print("Adding RA04-EN106 with art_id", art_id_val, "rarity", rarity)
                                        
                                    transformed_sets_by_lang[lang].append({
                                        "set_number": set_number, "set_name": set_name,
                                        "print_date": print_date, "rarity": rarity,
                                        "art_id": art_id_val, "suffix": suffixes[i] if suffixes else "",
                                        "image_url": None 
                                    })
                    if not artwork_matched:
                        transformed_sets_by_lang[lang].append({
                            "set_number": set_number, "set_name": set_name,
                            "print_date": print_date, "rarity": rarity,
                            "art_id": 1, "suffix": "", "image_url": None
                        })
                else:
                    transformed_sets_by_lang[lang].append({
                        "set_number": set_number, "set_name": set_name,
                        "print_date": print_date, "rarity": rarity,
                        "art_id": 1, "suffix": "", "image_url": None
                    })

    final_sets = {}
    for lang, prints in transformed_sets_by_lang.items():
        if prints:
            valid_prints = []
            errors = []
            for p in prints:
                # Check for basic print validity
                if p is None or not p.get("print_date") or not p.get("rarity"):
                    continue

                rarity = p["rarity"]
                
                # Check if rarity is in RARITY_ORDER
                if rarity not in RARITY_ORDER:
                    errors.append(f"Unknown rarity found: '{rarity}' for language {lang}")
                
                valid_prints.append(p)
            if len(errors) > 0:
                raise ValueError(errors)

            # Sort the prints using the updated rarities
            final_sets[lang] = sorted(
                valid_prints,
                key=lambda s: (s["print_date"], RARITY_ORDER[s["rarity"]]),
                reverse=True
            )
    return final_sets


def assign_image_urls_from_gallery(transformed_card, gallery_info, s3_webp_files):
    """Assigns image URLs to printings based on gallery information."""

    files_to_download = []

    if not gallery_info:
        return

    for lang in SUPPORTED_LANGUAGES:
        if lang not in transformed_card.get("sets", {}) or lang not in gallery_info:
            continue

        for printing in transformed_card["sets"][lang]:
            original_set_name = printing["set_name"]
            set_name = SET_EQUIVALENCES.get(original_set_name, original_set_name)
            if set_name != original_set_name: 
                printing["set_name"] = set_name
            set_number = printing["set_number"]
            rarity = printing["rarity"]
            suffix = printing.get("suffix", "")

            for gallery_print_info in gallery_info[lang]:
                gallery_set_name = gallery_print_info.get("set_name")
                gallery_set_number = gallery_print_info.get("set_number")
                gallery_rarity = gallery_print_info.get("rarity")
                if (gallery_set_name == set_name and
                    gallery_set_number == set_number and
                    gallery_rarity == RARITY_EQUIVALENCES.get(rarity, rarity)):
                    image_url_candidate = gallery_print_info.get("image_url")
                    if image_url_candidate:
                        if suffix and suffix in image_url_candidate:
                            printing["image_url"] = image_url_candidate
                            break
                        if not suffix:
                            printing["image_url"] = image_url_candidate
                            break
            if ("image_url" not in printing or printing["image_url"] is None) and \
                rarity in ["Common", "Short Print", "Super Short Print"]:
                for gallery_print_info in gallery_info[lang]:
                    if (gallery_print_info.get("set_name") == set_name and
                        gallery_print_info.get("set_number") == set_number and
                        gallery_print_info.get("rarity") in ["C", "SP", "SSP"] and 
                        gallery_print_info.get("image_url")):
                        printing["image_url"] = gallery_print_info["image_url"]
                        break
            if ("image_url" not in printing or printing["image_url"] is None) and \
                not any(ex_set in set_number for ex_set in EXCLUDED_FROM_DIAGNOSTIC_ERRORS):
                for gallery_print_info in gallery_info[lang]:
                    if gallery_print_info.get("set_name") == set_name and \
                        gallery_print_info.get("set_number") != set_number:
                        try:
                            g_parts = gallery_print_info.get("set_number", "").split('-', 1)
                            p_parts = set_number.split('-', 1)

                            if len(g_parts) == 2 and len(p_parts) == 2:
                                g_prefix, g_lang_code_num = g_parts
                                g_lang_code = g_lang_code_num[:-3]
                                p_prefix, p_lang_code_num = p_parts
                                p_lang_code = p_lang_code_num[:-3]
                                if g_prefix == p_prefix and g_lang_code == p_lang_code and DIAGNOSTIC_LOGGING:
                                    print(f"Potential Set number mismatch for {transformed_card.get('name',{}).get('en','UnknownCard')}: DB has {set_number}, Gallery has {gallery_print_info['set_number']}")
                        except (ValueError, AttributeError, TypeError):
                            if DIAGNOSTIC_LOGGING:
                                print(f"Could not parse set numbers for mismatch check: {set_number}, {gallery_print_info.get('set_number')} for card {transformed_card.get('name',{}).get('en','UnknownCard')}")
                

    for lang in SUPPORTED_LANGUAGES:
        if lang not in transformed_card.get("sets", {}):
            continue
        for printing in transformed_card["sets"][lang]:
            if "image_url" in printing and printing["image_url"] is not None:
                image_url = printing["image_url"]
                image_url_no_ext = image_url.split("/")[-1].rsplit('.', 1)[0]
                image_file_as_webp = "webp/" + image_url_no_ext + ".webp"
                image_file_as_webp = re.sub(r'%[0-9A-Fa-f]{2}', '', image_file_as_webp)
                printing["image_url"] = "https://r2.spellbook.life/" + image_file_as_webp
                if image_file_as_webp not in s3_webp_files:
                    files_to_download.append(image_url)

    if files_to_download and UPDATE_S3:
        print(f"Downloading {len(files_to_download)} images for {transformed_card.get('name',{}).get('en','UnknownCard')}")
        for image_url in files_to_download:
            output_path = Path(BASE_DIR, "temp_images", image_url.split("/")[-1])
            if download_transform_and_upload_image(image_url, output_path):
                print(f"Successfully processed image: {image_url}")
            else:
                print(f"Failed to process image: {image_url}")

def update_card_statuses(transformed_card, loaded_data, raw_card_limit_reg):
    """Updates banlist statuses for Advanced, OCG, Time Wizard formats, and Common Charity."""
    card_name_en = transformed_card.get('name',{}).get('en')
    if not card_name_en:
        return

    adv_banlist = loaded_data.get("advanced_banlist_data", {})
    formats_list = loaded_data.get("formats_list", [])
    filtered_sets_by_format = loaded_data.get("filtered_sets_by_format", {})

    transformed_card["status"] = {
        "Advanced": raw_card_limit_reg.get("tcg", UNRELEASED),
        "OCG": raw_card_limit_reg.get("ocg", UNRELEASED),
        "tw": {} 
    }
    if transformed_card["status"]["Advanced"] == "Not yet released":
        transformed_card["status"]["Advanced"] = UNRELEASED
    if transformed_card["status"]["OCG"] == "Not yet released":
        transformed_card["status"]["OCG"] = UNRELEASED

    today = datetime.now().strftime("%Y-%m-%d")
    has_released_tcg_printing = any(
        printing.get("print_date", "9999-12-31") <= today
        for lang in TCG_LANGUAGES
        if lang in transformed_card.get("sets", {})
        for printing in transformed_card["sets"][lang]
    )

    if not has_released_tcg_printing:
        transformed_card["status"]["Advanced"] = UNRELEASED
        transformed_card["status"]["Common Charity"] = UNRELEASED
        return

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
                    if printing.get("set_number","")[:4] in EXCLUDED_SETS_TIME_WIZARD:
                        continue

                    normalized_print_set_name = SET_EQUIVALENCES.get(printing.get("set_name",""), printing.get("set_name","")).lower()
                    if fmt_name in filtered_sets_by_format:
                        for legal_set in filtered_sets_by_format[fmt_name]:
                            normalized_legal_set_name = SET_EQUIVALENCES.get(legal_set.get("set_name",""), legal_set.get("set_name","")).lower()
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
    """Adds Master Duel (MD) and Duel Links (DL) data to the card."""
    card_name_en = transformed_card.get('name',{}).get('en')
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
        # Check other languages for main image
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

    md_card_data = next((c for c in md_cards_list if c.get("name","").lower() == card_name_en.lower()), None)
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

    dl_card_data = next((c for c in dl_cards_list if c.get("name","").lower() == card_name_en.lower()), None)
    if dl_card_data:
        transformed_card["status"]["DL"] = dl_card_data.get("status", UNRELEASED)
        transformed_card["dl_prints"] = dl_card_data.get("prints", [])
        if main_image_file:
            for dl_print in transformed_card["dl_prints"]:
                dl_print["image_url"] = main_image_file
    else:
        transformed_card["status"]["DL"] = UNRELEASED


def add_banlist_history(transformed_card, loaded_data):
    """Adds detailed TCG banlist history to the card."""
    card_name_en = transformed_card.get('name',{}).get('en')
    if not card_name_en:
        return

    tcg_banlists_map = loaded_data.get("tcg_banlists_map", {})
    transformed_card["banlist_data"] = {}

    earliest_tcg_print_date = None
    if "en" in transformed_card.get("sets", {}):
        for printing in transformed_card["sets"]["en"]:
            if printing.get("set_number","")[:4] in EXCLUDED_SETS_TIME_WIZARD:
                continue
            current_print_date = printing.get("print_date")
            if current_print_date and (earliest_tcg_print_date is None or current_print_date < earliest_tcg_print_date):
                earliest_tcg_print_date = current_print_date

    if earliest_tcg_print_date is None:
        for lang_sets in transformed_card.get("sets", {}).values():
            for printing in lang_sets:
                if printing.get("set_number","")[:4] in EXCLUDED_SETS_TIME_WIZARD:
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
    """Adds detailed Master Duel banlist history to the card."""
    card_name_en = transformed_card.get('name', {}).get('en')
    if not card_name_en:
        if DIAGNOSTIC_LOGGING:
            print("Skipping MD banlist history for card with no English name.")
        return

    md_banlists_map = loaded_data.get("md_banlists_map", {})
    transformed_card["md_banlist_data"] = {}

    md_release_date = transformed_card.get("md_release") 

    if not md_banlists_map:
        if DIAGNOSTIC_LOGGING:
            print(f"No Master Duel banlists loaded. Skipping MD banlist history for {card_name_en}.")
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

def process_single_card(raw_card_data, loaded_data, s3_webp_files):
    """Processes a single card from the raw dataset."""
        
    transformed_card = {}
    names = get_localized_value(raw_card_data, "name")
    if not names or "en" not in names:
        return None
    
    transformed_card["name"] = names
    card_name_en = names["en"]
    konami_id = raw_card_data.get("konami_id")

    if not transform_basic_card_info(raw_card_data, transformed_card):
        #print(f"Skipping {card_name_en} due to missing konami_id.")
        return None
    
    if UPDATE_ONLY_1_CARD:
        if konami_id != CARD_TO_UPDATE:
            return None
    
    if UPDATE_ONLY_GENESYS_POINTED_CARDS:
        if card_name_en not in loaded_data.get("genesys_points", {}) and card_name_en not in loaded_data.get("currently_pointed_cards", []):
            return None

    print(f"Processing card: {card_name_en} (Konami ID: {konami_id}, password: {transformed_card.get('card_id', 'N/A')})")

    if "text" in raw_card_data:
        transformed_card["text"] = get_localized_value(raw_card_data, "text")
    if "pendulum_effect" in raw_card_data:
        transformed_card["pendulum_effect"] = get_localized_value(raw_card_data, "pendulum_effect")

    with StepTimer("process_card_sets"):
        raw_sets = raw_card_data.get("sets", {})
        processed_sets = process_card_sets(raw_sets, card_name_en, loaded_data)
        transformed_card["sets"] = processed_sets

    gallery_card_name = card_name_en
    if transformed_card.get("card_id") == ARKANA_DM_ID:
        gallery_card_name = "Dark Magician (Arkana)"
    elif transformed_card.get("card_id") == FUSION_ID:
        gallery_card_name = "Polymerization (alternate password)"

    assign_genesys_points(transformed_card, loaded_data["genesys_points"])

    with StepTimer("get_card_gallery"):
        gallery_info = get_card_gallery(card_name=gallery_card_name, use_cache=USE_CACHE)
    with StepTimer("assign_image_urls_from_gallery"):
        assign_image_urls_from_gallery(transformed_card, gallery_info, s3_webp_files)

    with StepTimer("update_card_statuses"):
        update_card_statuses(transformed_card, loaded_data, raw_card_data.get("limit_regulation", {}))
    with StepTimer("add_videogame_data"):
        add_videogame_data(transformed_card, loaded_data)

    if card_name_en in loaded_data.get("artwork_urls_map", {}):
        transformed_card["artwork_urls"] = loaded_data["artwork_urls_map"][card_name_en]

    with StepTimer("assign_files"):
        for lang_prints_key in list(transformed_card.get("sets", {}).keys()):
            lang_prints = transformed_card["sets"][lang_prints_key]
            for printing in lang_prints:
                if printing.get("image_url"):
                    printing["file"] = printing["image_url"].split("/")[-1]
    
    with StepTimer("add_banlist_history"):
        add_banlist_history(transformed_card, loaded_data)
    with StepTimer("add_md_banlist_history"):
        add_md_banlist_history(transformed_card, loaded_data)

    return transformed_card


def process_all_cards(raw_dataset, loaded_data, s3_webp_files):
    """Processes all cards from the dataset."""
    processed_cards = []
    if not isinstance(raw_dataset, list):
        print(f"Error: raw_dataset is not a list ({type(raw_dataset)}). Cannot process cards.")
        return []
    raw_dataset.sort(key=lambda card: card.get("name", {}).get("en", ""))

    for raw_card in raw_dataset:
        processed_card = process_single_card(raw_card, loaded_data, s3_webp_files)
        if processed_card:
            processed_cards.append(processed_card)
    regular_dm = next((c for c in processed_cards if c.get("card_id") == REGULAR_DM_ID), None)
    arkana_dm = next((c for c in processed_cards if c.get("card_id") == ARKANA_DM_ID), None)

    if regular_dm and arkana_dm:
        # Create a new list excluding the original DM cards
        new_processed_cards = [c for c in processed_cards if c.get("card_id") not in [REGULAR_DM_ID, ARKANA_DM_ID]]
        for lang in SUPPORTED_LANGUAGES:
            if lang in arkana_dm.get("sets", {}):
                regular_dm_sets_lang = regular_dm.setdefault("sets", {}).setdefault(lang, [])
                regular_dm_sets_lang.extend(arkana_dm["sets"][lang])
                regular_dm_sets_lang.sort(key=lambda s: s["print_date"], reverse=True)
                # Remove duplicates: keep only unique (set_number, rarity, art_id)
                seen = set()
                unique_prints = []
                for p in regular_dm_sets_lang:
                    key = (p.get("set_number"), p.get("rarity"), p.get("art_id"))
                    if key not in seen:
                        seen.add(key)
                        unique_prints.append(p)
                regular_dm["sets"][lang] = unique_prints

        new_processed_cards.append(regular_dm)
        processed_cards = new_processed_cards


    poly_card = next((c for c in processed_cards if c.get("card_id") == POLY_ID), None)
    fusion_alt_poly_card = next((c for c in processed_cards if c.get("card_id") == FUSION_ID), None)

    if poly_card and fusion_alt_poly_card:
        new_processed_cards = [c for c in processed_cards if c.get("card_id") not in [POLY_ID, FUSION_ID]]
        for lang in SUPPORTED_LANGUAGES:
            if lang in fusion_alt_poly_card["sets"]:
                poly_card_sets_lang = poly_card["sets"][lang] + fusion_alt_poly_card["sets"][lang] 
                poly_card_sets_lang.sort(key=lambda s: s["print_date"], reverse=True)
                
                seen = set()
                unique_prints = []
                for p in poly_card_sets_lang:
                    key = (p.get("set_number"), p.get("rarity"), p.get("art_id"))
                    if key not in seen:
                        seen.add(key)
                        unique_prints.append(p)
                poly_card["sets"][lang] = unique_prints
        new_processed_cards.append(poly_card)
        processed_cards = new_processed_cards

    processed_cards.sort(key=lambda card: card.get("name", {}).get("en", ""))
    return processed_cards


def update_databases(processed_data, db_collections):
    """Updates MongoDB databases with processed card data using bulk operations."""
    if not UPDATE_DATABASE or not db_collections:
        print("Database update skipped.")
        return

    print("Updating MongoDB...")
    spellbook_dev_db = db_collections.get("spellbook_dev_db")
    spellbook_prod_db = db_collections.get("spellbook_prod_db")

    # Build bulk operations
    dev_ops = []
    prod_ops = []
    for card_data in processed_data:
        if "image_url" not in card_data or card_data["image_url"] is None:
            continue  # Skip cards without image URLs
        konami_id = card_data.get("_id")
        dev_ops.append(pymongo.ReplaceOne({"_id": konami_id}, card_data, upsert=True))
        prod_ops.append(pymongo.ReplaceOne({"_id": konami_id}, card_data, upsert=True))
        if len(dev_ops) >= 500:
            spellbook_dev_db.bulk_write(dev_ops, ordered=False)
            spellbook_prod_db.bulk_write(prod_ops, ordered=False)
            dev_ops = []
            prod_ops = []

    if dev_ops:
        spellbook_dev_db.bulk_write(dev_ops, ordered=False)
        spellbook_prod_db.bulk_write(prod_ops, ordered=False)
    print("MongoDB update complete.")


def cleanup_temp_files():
    """Deletes temporary files and directories, like mediawiki_test."""
    print("Deleting mediawiki_test directory...")
    if MEDIAWIKI_TEST_PATH.exists() and MEDIAWIKI_TEST_PATH.is_dir():
        for item in MEDIAWIKI_TEST_PATH.iterdir():
            if item.is_file():
                try:
                    item.unlink()
                except OSError as e:
                    print(f"Error deleting file {item}: {e}")
            elif item.is_dir():
                # More robust recursive delete for subdirectories
                try:
                    shutil.rmtree(item)
                except OSError as e:
                    print(f"Error deleting directory {item} recursively: {e}")
        # After deleting contents, attempt to delete the main directory if empty
        try:
            MEDIAWIKI_TEST_PATH.rmdir()
            print("mediawiki_test directory and its contents deleted.")
        except OSError :
            print(f"Could not delete {MEDIAWIKI_TEST_PATH} itself. It might not be empty or permissions issue.")
    else:
        print("mediawiki_test directory not found, skipping deletion.")

# --- Main Execution ---
def main():
    """Main function to run the card processing script."""
    total_start = time.time()

    with StepTimer("get_mongo_databases"):
        db_collections = get_mongo_databases()
    
    with StepTimer("load_initial_data"):
        loaded_data = load_initial_data(db_collections)
    
    if UPDATE_S3 and not OVERWRITE_S3_FILES:
        with StepTimer("list_s3_files"):
            print("Listing all files in /webp in S3...")
            s3_webp_files = list_s3_files_in_webp()
            print(f"Found {len(s3_webp_files)} files in /webp in S3.")
            print("Listing all files in /art in S3...")
            s3_art_files = list_s3_art_files_in_webp()
            print(f"Found {len(s3_art_files)} files in /art in S3.")
    else:
        s3_webp_files = []
        s3_art_files = []

    with StepTimer("fetch_json_from_url"):
        print("Downloading main card dataset...")
        raw_card_dataset = fetch_json_from_url(DATASET_URL)
        if not raw_card_dataset: 
            print("Failed to download or parse main card dataset. Exiting.")
            return

    print("Main dataset downloaded. Starting card processing.")

    with StepTimer("process_all_cards"):
        processed_card_data = process_all_cards(raw_card_dataset, loaded_data, s3_webp_files)

    with StepTimer("save_json_file"):
        save_json_file(processed_card_data, OUTPUT_PATH)
    print(f"Processed data saved to {OUTPUT_PATH}")
    
    if UPDATE_S3:
        with StepTimer("upload_missing_arts"):
            print("Uploading missing card arts...")
            for card in processed_card_data:
                card_password = card["_id"]
                output_path = Path(BASE_DIR, "temp_images", f"{str(card_password)}.webp")
                filename = f"art/{card_password}.webp"
                if filename not in s3_art_files:
                    print(f'Uploading card art for {card["name"]["en"]}')
                    download_transform_and_upload_card_image(card, output_path)

    with StepTimer("update_databases"):
        update_databases(processed_card_data, db_collections)
    
    total_elapsed = time.time() - total_start
    print(f"\n[TIMING] Total execution time: {total_elapsed:.3f}s")

if __name__ == "__main__":
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_ERRORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser(description="Update the Excavate / Spellbook card database")
    parser.add_argument("--cache", type=str, default="0", help="Should the script use cached data for galleries? (default: False)")
    parser.add_argument("--s3", type=str, default="1", help="Should the script update S3 with new images? (default: True)")
    parser.add_argument("--log", type=str, default="0", help="Should the script log diagnostic information? (default: False)")
    parser.add_argument("--db", type=str, default="1", help="Should the script update the MongoDB databases? (default: True)")
    parser.add_argument("--vg", type=str, default="1", help="Should the script get updated videogame data from Dkayed? (default: True)")
    parser.add_argument("--card", type=int, default="0", help="Only process the specified konami id (default: 0)")
    parser.add_argument("--genesys", type=str, default="0", help="Only process pointed cards in Genesys format (default: 0)")
    parser.add_argument("--ows3", type=str, default=0, help="Overwrite files on S3? (default:False)")
    args = parser.parse_args()
    print(args)

    if args.cache is not None:
        USE_CACHE = args.cache.lower() in ["1", "true", "yes", "y"]
    if args.s3 is not None:
        UPDATE_S3 = args.s3.lower() in ["1", "true", "yes", "y"]
    if args.log is not None:
        DIAGNOSTIC_LOGGING = args.log.lower() in ["1", "true", "yes", "y"]
    if args.db is not None:
        UPDATE_DATABASE = args.db.lower() in ["1", "true", "yes", "y"]
    if args.vg is not None:
        UPDATE_VIDEOGAME_DATA = args.vg.lower() in ["1", "true", "yes", "y"]
    if args.genesys is not None:
        UPDATE_ONLY_GENESYS_POINTED_CARDS = args.genesys.lower() in ["1", "true", "yes", "y"]
    if args.card is not None and args.card != 0:
        UPDATE_ONLY_1_CARD = True
        CARD_TO_UPDATE = int(args.card)
    if args.ows3 is not None and args.ows3 != 0:
        OVERWRITE_S3_FILES = True

    main()
