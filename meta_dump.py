import json
import requests
import os
from pathlib import Path

MD_URL = "https://www.masterduelmeta.com/api/v1/cards?limit=3000&page="
DL_URL = "https://www.duellinksmeta.com/api/v1/cards?limit=3000&page="

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data" / "input"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MD_OUTPUT_FILE = DATA_DIR / "md_cards.json"
DL_OUTPUT_FILE = DATA_DIR / "dl_cards.json"

name_alias = [
    {"before":"\u2019", "after":"'"},
    {"before":"\u2013", "after":"-"},
    {"before":"\u00dc", "after":"Ü"},
    {"before":"\u00e9", "after":"é"},
    {"before":"\u201c", "after":'"'},
    {"before":"\u201d", "after":'"'},
    {"before":"Cu Chulainn", "after":"Cú Chulainn"},
    {"before":"Brionac, the Dragon of Icy Malevolence", "after":"Brionac, the Magical Ice Dragon"},
    {"before":"Marina, Princess of Sunflowers", "after":"Mariña, Princess of Sunflowers"},
    {"before":"Fiendish Engine Omega", "after":"Fiendish Engine Ω"},
    {"before":"Spell Reactor RE", "after":"Spell Reactor・RE"},
    {"before":"Summon Reactor SK", "after":"Summon Reactor・SK"},
    {"before":"Trap Reactor Y FI", "after":"Trap Reactor・Y FI"},
    {"before":"Falchion Beta", "after":"Falchionβ"},
    {"before":"Damage Vaccine Omega MAX", "after":"Damage Vaccine Ω MAX"},
    {"before":"Machine Lord Ur", "after":"Machine Lord Ür"},
    {"before":"Dandy White Lion", "after":"Dandy Whitelion"},
    {"before":"Lil-la-Rap", "after":"Lil-la Rap"},
    {"before":"Synchro Blast Wave", "after":"Synch Blast Wave"},
    {"before":"Synchronized Realm", "after":"Synch Realm"},
    {"before": "Maliss P Dormouse", "after": "Maliss <P> Dormouse"},
    {"before": "Trickstar Band Drummatis", "after": "Trickstar Band Drumatis"},
    {"before": "Twin Long Rods 1", "after": "Twin Long Rods #1"},
    {"before": "Leo Wizard the Dark Fiend", "after": "Leo Wizard, the Dark Mage"}
]

def dump_database(duel_links=False):
    cards = []
    raw_cards = []
    if duel_links:
        url = DL_URL
        output = DL_OUTPUT_FILE
    else:
        url = MD_URL
        output = MD_OUTPUT_FILE
    for page in range(1, 1000):
        print(f"Dumping page {page}")
        response = requests.get(f"{url}{page}", timeout=100).json()
        if len(response) == 0:
            break
        for raw_card in response:
            raw_cards.append(raw_card)
            name:str = raw_card["name"].lstrip()
            for alias in name_alias:
                name = name.replace(alias["before"], alias["after"])
            if "banStatus" in raw_card:
                status = raw_card["banStatus"]
                if status is None:
                    status = "Unlimited"
                if not duel_links:
                    if status == "Limited 1":
                        status = "Limited"
                    elif status == "Limited 2":
                        status = "Semi-Limited"
            else:
                status = "Unlimited"
                
            if "rarity" in raw_card:
                rarity = raw_card["rarity"]
            else:
                rarity = None
                if status == "Unlimited":
                    status = "Unreleased"
            if "release" in raw_card:
                release = raw_card["release"]
                if release:
                    release = release.split("T")[0]
            elif "nameRelease" in raw_card:
                release = raw_card["nameRelease"]
                if release:
                    release = release.split("T")[0]
            else:
                release = None
            
            if "tcgRelease" in raw_card:
                tcg_release = raw_card["tcgRelease"]
                if tcg_release:
                    tcg_release = tcg_release.split("T")[0]
            else:
                tcg_release = None
            
            if "ocgRelease" in raw_card:
                ocg_release = raw_card["ocgRelease"]
                if ocg_release:
                    ocg_release = ocg_release.split("T")[0]
            else:
                ocg_release = None
                    
            prints = []
            for printing in raw_card["obtain"]:
                if "source" not in printing or printing["source"] is None:
                    # Shit like vanilla BLS
                    continue
                try:
                    if "type" in printing["source"]:
                        print_name = f"{printing['source']['type']}: {printing['source']['name']}"
                    else:
                        print_name = printing["source"]["name"]
                    prints.append({
                        "name":print_name,
                        "rarity":rarity
                    })
                except KeyError as e:
                    print(printing)
                    raise e
                except TypeError as e:
                    print(raw_card)
                    raise e
            existing_card = next((card for card in cards if card["name"].lstrip() == name), None)
            if existing_card:
                existing_card["prints"].extend(prints)
                if tcg_release is not None:
                    if existing_card["tcg_release"] is None:
                        existing_card["tcg_release"] = tcg_release
                if ocg_release is not None:
                    if existing_card["ocg_release"] is None:
                        existing_card["ocg_release"] = ocg_release
            else:
                cards.append({
                    "name":name,
                    "status":status,
                    "prints":prints,
                    "release":release,
                    "tcg_release": tcg_release,
                    "ocg_release": ocg_release
                })

    with open(output, "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=4, ensure_ascii=False)

def dump_all():
    dump_database(duel_links=False)
    dump_database(duel_links=True)

if __name__ == "__main__":
    dump_all()