import json
import time
import os
from pathlib import Path
import urllib3
import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import ReadTimeoutError

API_URL = "https://yugipedia.com/api.php"

BASE_DIR = Path(__file__).resolve().parent.parent

CACHE_DIR = BASE_DIR / "mediawiki_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

set_equivalences = {
    "Premium Pack (TCG)": "Premium Pack",
    "Premium Pack 2 (TCG)": "Premium Pack 2",
    "Yu-Gi-Oh! Championship Series 2011 Prize Card": "Yu-Gi-Oh! Championship Series Prize Cards",
    "Ghosts From the Past (set)": "Ghosts From the Past",
    "Duel Terminal 5a": "Duel Terminal 5",
    "Duel Terminal 5b": "Duel Terminal 5",
    "Duel Terminal 6a": "Duel Terminal 6",
    "Duel Terminal 6b": "Duel Terminal 6",
    "Duel Terminal 7a": "Duel Terminal 7",
    "Duel Terminal 7b": "Duel Terminal 7",
    "Magic Ruler": "Spell Ruler",
    "Structure Deck: Marik (TCG)": "Structure Deck: Marik",
    "Shadow of Infinity Sneak Peek participation card": "Shadow of Infinity Sneak Peek Participation Card",
    "Yu-Gi-Oh! 5D's Duel Transer Promotional Cards": "Yu-Gi-Oh! 5D's Duel Transer promotional cards",
    "Maximum Crisis Special Edition": "Maximum Crisis: Special Edition",
    "Yu-Gi-Oh! 5D's volume 8 promotional card": "Yu-Gi-Oh! 5D's Volume 8 promotional card",
    "2002 Booster Pack Tins": "Booster Pack Collectors Tins 2002",
    "Dark Revelation Volume 2": "Dark Revelation 2",
    "2015 Mega-Tin": "2015 Mega-Tins"
}

DIAGNOSTIC_LOGGING = False

RETRIES = 300

def transform_image_url(url):
    if ("//thumb") not in url:
        return url
    url = url.replace("//thumb/", "//")
    last_slash_index = url.rfind("/")
    if last_slash_index != -1:
        url = url[:last_slash_index]

    return url


def get_card_gallery(card_name: str, use_cache:bool):
    """
    Fetch card gallery information from Yugipedia for a given card name.
    Returns None if the page doesn't exist or there's an error.
    """

    # Sanitize card_name to remove invalid characters for file names
    sanitized_card_name = "".join(c for c in card_name if c.isalnum() or c in (" ", "-", "_"))

    # Check for cache
    cache_file_path = os.path.join(CACHE_DIR, f"{sanitized_card_name}.json")
    if os.path.exists(cache_file_path):
        cache_age = time.time() - os.path.getmtime(cache_file_path)
        if cache_age < 1209600 and use_cache:  # 1209600 seconds = 2 weeks
            with open(cache_file_path, 'r', encoding="utf-8") as cache_file:
                try:
                    return json.load(cache_file)
                except json.decoder.JSONDecodeError:
                    print("Faulty cache, downloading again")

    card_name = card_name.replace("#", "").replace("<", "").replace(">", "")

    # Format the title for the gallery page
    gallery_title = f"Card Gallery:{card_name}"

    # Parameters for the API request
    params = {
        "action": "parse",
        "page": gallery_title,
        "format": "json",
        "prop": "sections|text",  # Get both sections and main text
        "formatversion": "2",  # Use newer format version for cleaner output
    }

    # Custom user-agent to identify the requester
    headers = {
        'User-Agent': 'Excavate by DiamondDude/1.0 (https://www.excavate.top)'
    }

    # Firefox user agent

    for _ in range(RETRIES):
        try:
            response = requests.get(API_URL, params=params, headers=headers, timeout=120)

            # Check for specific error codes
            if response.status_code == 520:
                if DIAGNOSTIC_LOGGING:
                    print(
                        f"Received status code 520 for {card_name}. Retrying in 10 seconds..."
                    )
                time.sleep(10)  # Wait before retrying
                continue  # Retry the request
            elif response.status_code == 429:
                if DIAGNOSTIC_LOGGING:
                    print(
                        f"Received status code 429 for {card_name}. Retrying in 10 seconds..."
                    )
                time.sleep(10)  # Wait before retrying
                continue  # Retry the request
            elif response.status_code == 403:
                if DIAGNOSTIC_LOGGING:
                    print(
                        f"Received status code 403 for {card_name}. Retrying in 10 seconds..."
                    )
                    print(f"Response content: {response.text}")  # Log response content
                    print(f"Request parameters: {params}")  # Log request parameters
                    print(f"Response headers: {response.headers}")  # Log response headers
                time.sleep(10)  # Wait before retrying
                continue  # Retry the request
            elif response.status_code == 502:
                if DIAGNOSTIC_LOGGING:
                    print(f"Received status code 502 for {card_name}. Retrying in 10 seconds...")
                time.sleep(10)
            elif response.status_code == 503:
                # Service temporarily unavailable: Try again in 10 seconds
                if DIAGNOSTIC_LOGGING:
                    print(f"Received status code 503 for {card_name}. Retrying in 10 seconds...")
                time.sleep(10)
                continue
            try:
                data = response.json()
            except requests.exceptions.JSONDecodeError:
                time.sleep(10)
                continue
            except Exception:
                time.sleep(10)
                continue

            if "error" in data:
                if not "(card)" in card_name:
                    # Some cards have " (card)" appended to the card name because their names are the same as some other page
                    # Some examples include "Ancient Gear" and "Absolute Powerforce"
                    # Instead of caching all of these card names, we query for the card gallery, and if it fails, we try again with (card)
                    return get_card_gallery(card_name=f"{card_name} (card)", use_cache=use_cache)
                if DIAGNOSTIC_LOGGING:
                    print(
                        f"Error fetching gallery for {card_name}: {data['error'].get('info', 'Unknown error')}"
                    )
                    print(response.status_code)
                return None

            if "parse" not in data:
                print(f"No gallery found for {card_name}")
                return None

            result = {}
            content = data["parse"]["text"]
            soup = BeautifulSoup(content, "html.parser")

            # Map of gallery IDs to their section names in the result
            gallery_sections = {
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
            # Find all card gallery divs
            for gallery_id, section_name in gallery_sections.items():
                if "Video games" in section_name:
                    continue  # Ignore sections containing "Video games"

                gallery_div = soup.find("div", id=gallery_id)
                if gallery_div:
                    # Merge sections as needed
                    if section_name in [
                        "Worldwide English",
                        "North American English",
                        "European English",
                        "Australian English",
                    ]:
                        if "en" not in result:
                            result["en"] = []
                        # Process each print entry in this gallery
                        for li in gallery_div.find_all("li", class_="gallerybox"):
                            print_info = extract_print_info(li)
                            if print_info:
                                for info in print_info:
                                    result["en"].append(info)
                    else:
                        # Rename sections for other languages
                        lang_code = {
                            "French": "fr",
                            "French-Canadian": "fr",
                            "German": "de",
                            "Italian": "it",
                            "Portuguese": "pt",
                            "Spanish": "es",
                            "Japanese": "ja",
                            "Korean": "ko",
                            "Asian-English": "ae",
                            "Simplified Chinese": "sc",
                        }.get(section_name)

                        if lang_code:
                            if lang_code not in result:
                                result[lang_code] = []
                            # Process each print entry in this gallery
                            for li in gallery_div.find_all("li", class_="gallerybox"):
                                print_info = extract_print_info(li)
                                if print_info:
                                    for info in print_info:
                                        result[lang_code].append(info)

            language_equivalences = {
                "English": "en",
                "French": "fr",
                "German": "de",
                "Italian": "it",
                "Portuguese": "pt",
                "Spanish": "es",
                "Japanese": "ja",
                "Korean": "ko",
                "Asian-English": "ae",
                "Simplified Chinese": "sc",
            }

            # Check for the table structure and extract information
            tables = soup.find_all("table", class_="card-galleries")
            for table in tables:
                language_text = table.find("th").get_text()
                language_code = "en"
                for language, code in language_equivalences.items():
                    if language in language_text:
                        language_code = code
                        break

                gallery_boxes = table.find_all(
                    "ul", class_="gallery mw-gallery-traditional"
                )
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
                            if DIAGNOSTIC_LOGGING:
                                print("Case topper detected: ignoring")
                            continue
                        if links:
                            if links[1].get_text() == "Official Proxy":
                                continue
                            print_info_array = []
                            print_info = {}
                            if image and "src" in image.attrs:
                                print_info["image_url"] = transform_image_url(
                                    image["src"]
                                )
                            else:
                                print_info["image_url"] = None

                            print_info["set_number"] = links[0].get_text()
                            print_info["rarity"] = links[1].get_text()
                            print_info["edition"] = links[2].get_text()
                            print_info["set_name"] = links[3].get("title")
                            print_info["set_name"] = set_equivalences.get(
                                print_info["set_name"], print_info["set_name"]
                            )
                            print_info_array.append(print_info)
                            if len(links) > 4:
                                print_info_array.append(
                                    {
                                        "set_number": links[0].get_text(),
                                        "rarity": links[1].get_text(),
                                        "edition": links[2].get_text(),
                                        "set_name": set_equivalences.get(
                                            links[4].get("title"), links[4].get("title")
                                        ),
                                        "image_url": transform_image_url(image["src"]),
                                    }
                                )

                            if language_code not in result:
                                result[language_code] = []
                            for print_info in print_info_array:
                                result[language_code].append(print_info)
                # Save the result to cache
            if result:
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(cache_file_path, 'w', encoding="utf-8") as cache_file:
                    json.dump(result, cache_file)

            return result

        except TimeoutError:
            time.sleep(10)
        except requests.exceptions.ReadTimeout:
            time.sleep(10)
        except urllib3.exceptions.ProtocolError:
            time.sleep(10)
        except requests.exceptions.ConnectionError:
            time.sleep(10)
        except ReadTimeoutError:
            time.sleep(10)
        except Exception:
            time.sleep(10)

    print(f"Failed to fetch gallery for {card_name} after multiple attempts.")
    return None




def extract_print_info(li):
    """Extract print information from a gallery box."""
    print_info = {}
    gallery_text = li.find("div", class_="gallerytext")
    if gallery_text:
        links = gallery_text.find_all("a")
        img = li.find("img")
        if img and "src" in img.attrs:
            print_info["image_url"] = transform_image_url(img["src"])
        else:
            print_info["image_url"] = None
        if len(links) == 3 and ("-JP" in links[0].get("title") or "-SC" in links[0].get("title")):
            if links[1].get_text() == "Official Proxy":
                return None
            print_info["set_number"] = links[0].get_text()
            print_info["rarity"] = links[1].get_text()
            print_info["set_name"] = links[2].get("title")
            print_info["set_name"] = set_equivalences.get(
                print_info["set_name"], print_info["set_name"]
            )
            print_info["edition"] = None
            return [print_info]
        if len(links) < 4:
            return None
        if links:
            for link in links:
                title = link.get("title")
                if title and "Giant Card" in title:
                    return None
            print_info["set_number"] = links[0].get_text()
            print_info["rarity"] = links[1].get_text()
            print_info["edition"] = links[2].get_text()
            print_info["set_name"] = links[3].get("title")
            print_info["set_name"] = set_equivalences.get(
                print_info["set_name"], print_info["set_name"]
            )
            if len(links) > 4:
                print_info_2 = {
                    "set_number": links[0].get_text(),
                    "rarity": links[1].get_text(),
                    "edition": links[2].get_text(),
                    "set_name": set_equivalences.get(
                        links[4].get("title"), links[4].get("title")
                    ),
                    "image_url": print_info["image_url"]
                }
                return [print_info, print_info_2]

    return [print_info]


if __name__ == "__main__":
    DIAGNOSTIC_LOGGING = True
    result = get_card_gallery(card_name="Anti-Spell Fragrance", use_cache=False)
    if result:
        print(json.dumps(result["en"], indent=4))