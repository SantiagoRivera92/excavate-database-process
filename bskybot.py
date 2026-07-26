import io
import os
import requests
from atproto import Client, client_utils
from PIL import Image
from urllib.parse import quote

BSKY_ACCOUNT_NAME = os.environ.get("EXCAVATE_CARDS_BSKY_ACCOUNT")
BSKY_PASSWORD = os.environ.get("EXCAVATE_CARDS_BSKY_APP_PASSWORD")
MAX_IMAGE_BYTES = 1024 * 1024
MAX_RESIZE_ATTEMPTS = 8

client = Client()
client.login(BSKY_ACCOUNT_NAME, BSKY_PASSWORD)

def compress_image_under_limit(img_data, card_name):
    """Shrink image data under Bluesky's 1MB limit with a hard attempt cap."""
    if len(img_data) <= MAX_IMAGE_BYTES:
        return img_data

    img = Image.open(io.BytesIO(img_data))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    max_dim = 1024
    quality = 85
    for attempt in range(1, MAX_RESIZE_ATTEMPTS + 1):
        print(
            f"Image for card {card_name} exceeds 1 MB "
            f"({len(img_data)} bytes). Compressing attempt {attempt}/{MAX_RESIZE_ATTEMPTS}..."
        )
        working = img.copy()
        working.thumbnail((max_dim, max_dim))
        img_buffer = io.BytesIO()
        working.save(img_buffer, format="JPEG", quality=quality, optimize=True)
        img_data = img_buffer.getvalue()
        if len(img_data) <= MAX_IMAGE_BYTES:
            return img_data
        quality = max(35, quality - 10)
        max_dim = max(256, int(max_dim * 0.8))

    return None

def post_card():
    random_card = requests.get("https://www.excavate.top/api/v1/randomcard", timeout=10).json()

    card_name = random_card["name"]["en"]
    konami_id = random_card["konami_id"]
    print(f"Got {card_name} at random")

    query = f'"{card_name}"'
    search_url = f"https://www.excavate.top/api/v1/cards?q={quote(query)}"
    search_results = requests.get(search_url, timeout=10).json()

    card = next(c for c in search_results["cards"] if c["konami_id"] == konami_id)
    card_text = card.get("text", {}).get("en", "")

    text = f"{card_name}"
    if card["card_type"] == "Monster":
        text += f"\n\n{card['attribute']} / {card['typeline']}"
        if "Xyz" in card["typeline"]:
            text += f" • Rank {card['level']} • ATK: {card['atk']} / DEF: {card['def']}"
        elif "Link" in card["typeline"]:
            text += f" • Link {card['level']} • ATK: {card['atk']}"
        else:
            text += f" • Level {card['level']} • ATK: {card['atk']} / DEF: {card['def']}"
    else:
        text += f"\n\n{card['typeline']} {card['card_type']}"

    if card_text:
        text += f"\n\n{card_text}"

    image_url = "https://r2.spellbook.life/webp/" + card["image_url"]
    url = f"https://www.excavate.top/card/{konami_id}"

    text_builder = client_utils.TextBuilder()
    text_builder.link(card_name, url)

    try:
        response = requests.get(image_url, timeout=200)
        response.raise_for_status()
        img_data = compress_image_under_limit(response.content, card_name)
        if img_data is None:
            print(f"Could not compress image for {card_name} under 1 MB; skipping post.")
            return

        print(f"Posting {card_name}")
        client.send_image(
            text=text_builder,
            image=img_data,
            image_alt=text
        )
    except requests.RequestException as e:
        print(f"Failed to download image for card {card_name}: {e}")
    except Exception as e:
        print(f"An error occurred while processing the image for card {card_name}: {e}")


post_card()
