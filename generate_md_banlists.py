from pathlib import Path
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup

API_URL = "https://yugipedia.com/api.php"

BASE_DIR = Path(__file__).parent.resolve()

FORMATS_DIR = BASE_DIR / "data/formats_md"

CATEGORY_NAME = "Category:Yu-Gi-Oh!_Master_Duel_Forbidden_&_Limited_Lists"

def extract_banlist(page_title):
    params = {
        "action": "parse",
        "page": page_title,
        "format": "json",
        "prop": "sections|text",
        "formatversion": "2",
    }

    headers = {
        'User-Agent': 'Spellbook by DiamondDude/1.0 (https://spellbook.life)'
    }
    data = None
    while (data is None):
        response = requests.get(API_URL, params=params, headers=headers, timeout=120)
        data = response.json()
    html = data.get("parse", {}).get("text", {})
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find_all("table", class_="card-list")[-1].find("tbody")
    banlist = []
    for row in table.find_all("tr"):
        tds = row.find_all("td")
        if tds:
            name = tds[0].get_text(strip=True)
            status = tds[-1].get_text(strip=True)
            banlist.append({"name": name, "status": status})

    date = None
    for row in soup.find_all("tr"):
        th = row.find("th")
        if th and th.get_text(strip=True) == "Effective date":
            infobox_data = row.find(class_="infobox-data")
            if infobox_data:
                raw_date = infobox_data.get_text(strip=True)
                date_obj = datetime.strptime(raw_date, "%B %d, %Y")
                date = date_obj.strftime("%Y-%m-%d")
            break
    result = {"forbidden": [], "limited": [], "semilimited": []}
    for card in banlist:
        status = card["status"].lower()
        name = card["name"]
        if status == "forbidden":
            result["forbidden"].append(name)
        elif status == "limited":
            result["limited"].append(name)
        elif status == "semi-limited":
            result["semilimited"].append(name)
    
    return date, result

def extract_banlist_pages():
    
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": CATEGORY_NAME,
        "cmlimit": "max",
        "format": "json"
    }

    headers = {
        'User-Agent': 'Spellbook by DiamondDude/1.0 (https://spellbook.life)'
    }

    response = requests.get(API_URL, params=params, headers=headers, timeout=120)
    print("Request URL:", response.url)
    data = response.json()
    pages = data.get("query", {}).get("categorymembers", [])
    pages = [
        page["title"] for page in pages if (
            "festival" not in page["title"].lower() and 
            "theme chronicle" not in page["title"].lower() and 
            "event" not in page["title"].lower() and
            "cup" not in page["title"].lower() and
            "legend anthology" not in page["title"].lower() and
            "link regulation" not in page["title"].lower() and
            "duel triangle" not in page["title"].lower()
            ) 
        ]
    return pages

banlists = extract_banlist_pages()
for banlist in banlists:
    print(f"Processing banlist: {banlist}")
    date, cards = extract_banlist(banlist)
    if not date:
        print(f"No effective date found for {banlist}, skipping.")
        continue

    filename = f"{date}.json"
    filepath = FORMATS_DIR / filename
    FORMATS_DIR.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=4, ensure_ascii=False)

    print(f"Saved banlist to {filepath}")