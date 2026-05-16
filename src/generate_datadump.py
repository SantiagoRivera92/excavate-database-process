import json
import os
from datetime import datetime, timezone
from pathlib import Path
from common import get_mongo_databases


MARKER_START = "<!-- datadump start -->"
MARKER_END = "<!-- datadump end -->"


def main():
    dbs = get_mongo_databases()
    collection = dbs["spellbook_prod_db"]

    cards = list(collection.find({}))
    for card in cards:
        card.pop("_id", None)
        if "status" in card:
            card["status"].pop("tw", None)

    output_path = Path(__file__).resolve().parent.parent / "datadump.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Generated datadump.json with {len(cards)} cards")

    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo:
        print("GITHUB_REPOSITORY not set, skipping README update")
        return

    tag = f"1.0.{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    download_url = f"https://github.com/{repo}/releases/download/{tag}/datadump.json"

    readme_path = Path(__file__).resolve().parent.parent / "README.md"
    readme = readme_path.read_text(encoding="utf-8")

    dump_section = (
        "## Latest Data Dump\n\n"
        f"[datadump.json]({download_url})\n"
    )

    if MARKER_START in readme and MARKER_END in readme:
        start_idx = readme.index(MARKER_START) + len(MARKER_START)
        end_idx = readme.index(MARKER_END)
        readme = readme[:start_idx] + "\n\n" + dump_section + "\n" + readme[end_idx:]
    else:
        readme += f"\n\n{MARKER_START}\n\n{dump_section}\n{MARKER_END}\n"

    readme_path.write_text(readme, encoding="utf-8")
    print("README.md updated with download link")


if __name__ == "__main__":
    main()
