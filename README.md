# Yu-Gi-Oh! Card Data Dumps

Automated nightly dumps of the Yu-Gi-Oh! card database. Each release contains all cards as a single JSON file.

This repo also does a lot of background stuff for the database. If you want to spin up your own version of the database just hit me up. Full disclosure, I went insane doing it and you will too.

Ideally this can lighten the load on the API so I don't have to fork over a bunch of money to a bunch of internet billionaire overlords.

## Download

Go to the [Releases](https://github.com/SantiagoRivera92/excavate-database-process/releases) page and download the latest `datadump.json`.

Releases are tagged by date: `1.0.YYYYMMDD`.

<!-- datadump start -->

## Latest Data Dump

[datadump.json](https://github.com/SantiagoRivera92/excavate-database-process/releases/download/1.0.20260624/datadump.json)

<!-- datadump end -->

## Data Format

Each release is a single JSON array of card objects. The arrays are arrays for a reason, I only put one element in them for this sample but obviously they will contain more.

```json
{
  "pages": 1,
  "cards": [
    {
      "name": {
        "en": "Dark Magician",
        "de": "Dunkler Magier",
        "es": "Mago Oscuro",
        "fr": "Magicien Sombre",
        "it": "Mago Nero",
        "pt": "Mago Negro",
        "ja": "\u30d6\u30e9\u30c3\u30af\u30fb\u30de\u30b8\u30b7\u30e3\u30f3",
        "ko": "\ube14\ub799 \ub9e4\uc9c0\uc158"
      },
      "konami_id": 4041,
      "card_id": 46986414,
      "card_type": "Monster",
      "typeline": "Spellcaster / Normal",
      "atk": 2500,
      "def": 2100,
      "level": 7,
      "archetypes": [
        "Dark Magician"
      ],
      "attribute": "DARK",
      "text": {
        "en": "The ultimate wizard in terms of attack and defense.",
        "de": "Der ultimative Hexer im Hinblick auf Angriff und Verteidigung.",
        "es": "El m\u00e1s grande de los magos en cuanto al ataque y la defensa.",
        "fr": "Mage supr\u00eame en termes d'attaque et de d\u00e9fense.",
        "it": "Il pi\u00f9 potente tra i maghi per abilit\u00e0 offensive e difensive.",
        "pt": "O mago definitivo em termos de ataque e defesa.",
        "ja": "\u9b54\u6cd5\u4f7f\u3044\u3068\u3057\u3066\u306f\u3001\u653b\u6483\u529b\u30fb\u5b88\u5099\u529b\u3068\u3082\u306b\u6700\u9ad8\u30af\u30e9\u30b9\u3002",
        "ko": "\ub9c8\ubc95\uc0ac \uc911\uc5d0\uc11c \uacf5\uaca9\ub825 / \uc218\ube44\ub825\uc774 \ub3d9\uc2dc\uc5d0 \uac00\uc7a5 \ub192\uc740 \uacc4\uae09."
      },
      "sets": {
        "en": [
          {
            "set_number": "RA05-EN083",
            "set_name": "Rarity Collection 5",
            "print_date": "2026-04-09",
            "rarity": "Starlight Rare",
            "art_id": 1,
            "suffix": "",
            "image_url": null
          }
        ],
        "de": [
          {
            "set_number": "RA05-DE083",
            "set_name": "Rarity Collection 5",
            "print_date": "2026-04-09",
            "rarity": "Starlight Rare",
            "art_id": 1,
            "suffix": "",
            "image_url": null
          }
        ],
        "es": [
          {
            "set_number": "RA05-SP083",
            "set_name": "Rarity Collection 5",
            "print_date": "2026-04-09",
            "rarity": "Starlight Rare",
            "art_id": 1,
            "suffix": "",
            "image_url": null
          }
        ],
        "fr": [
          {
            "set_number": "RA05-FR083",
            "set_name": "Rarity Collection 5",
            "print_date": "2026-04-09",
            "rarity": "Starlight Rare",
            "art_id": 1,
            "suffix": "",
            "image_url": null
          }
        ],
        "it": [
          {
            "set_number": "RA05-IT083",
            "set_name": "Rarity Collection 5",
            "print_date": "2026-04-09",
            "rarity": "Starlight Rare",
            "art_id": 1,
            "suffix": "",
            "image_url": null
          }
        ],
        "pt": [
          {
            "set_number": "RA05-PT083",
            "set_name": "Rarity Collection 5",
            "print_date": "2026-04-09",
            "rarity": "Starlight Rare",
            "art_id": 1,
            "suffix": "",
            "image_url": null
          }
        ],
        "ja": [
          {
            "set_number": "PGB1-JP011",
            "set_name": "Prismatic God Box",
            "print_date": "9999-12-31",
            "rarity": "Millennium Ultra Rare",
            "art_id": 1,
            "suffix": "",
            "image_url": null
          }
        ],
        "ko": [
          {
            "set_number": "MB01-KR010",
            "set_name": "Millennium Deck",
            "print_date": "9999-12-31",
            "rarity": "Millennium Rare",
            "art_id": 1,
            "suffix": "",
            "image_url": null
          }
        ]
      },
      "status": {
        "Advanced": "Unlimited",
        "OCG": "Unlimited",
        "Common Charity": "Unlimited",
        "MD": "Unreleased",
        "DL": "Unlimited"
      },
      "image_url": "DarkMagician-RA05-EN-UR-1E.webp",
      "md_prints": [
        {
          "name": "1st Anniversary Bundle",
          "rarity": "UR",
          "image_url": "DarkMagician-RA04-EN-QCScR-1E-AA.webp"
        }
      ],
      "md_release": "2022-01-19",
      "tcg_release": "2002-03-08",
      "dl_prints": [
        {
          "name": "Special Campaigns",
          "rarity": "UR",
          "image_url": "DarkMagician-RA04-EN-QCScR-1E-AA.webp"
        }
      ],
      "artwork_urls": [
        {
          "art_id": 1,
          "url": "DarkMagician-TF05-JP-VG-artwork.png"
        }
      ],
      "banlist_data": {
        "2006-12-21": 3,
        "2009-09-01": 3,
        "2008-09-01": 3,
        "2020-09-14": 3,
        "2020-12-15": 3,
        "2019-04-29": 3,
        "2011-09-01": 3,
        "2013-09-01": 3,
        "2025-09-12": 3,
        "2024-09-02": 3,
        "2017-03-31": 3,
        "2007-03-01": 3,
        "2022-05-17": 3,
        "2014-10-01": 3,
        "2022-10-03": 3,
        "2003-04-01": 3,
        "2024-04-13": 3,
        "2021-03-15": 3,
        "2020-06-15": 3,
        "2008-05-09": 3,
        "2023-06-05": 3,
        "2013-10-11": 3,
        "2021-10-01": 3,
        "2004-08-25": 3,
        "2022-11-21": 3,
        "2003-11-17": 3,
        "2024-12-09": 3,
        "2020-01-20": 3,
        "2008-03-01": 3,
        "2014-04-01": 3,
        "2003-08-25": 3,
        "2023-02-06": 3,
        "2019-07-15": 3,
        "2025-10-24": 3,
        "2019-01-29": 3,
        "2020-04-01": 3,
        "2009-03-01": 3,
        "2017-11-06": 3,
        "2006-04-01": 3,
        "2018-12-03": 3,
        "2012-03-01": 3,
        "2022-02-07": 3,
        "2016-02-08": 3,
        "2023-12-19": 3,
        "2004-04-19": 3,
        "2015-04-01": 3,
        "2004-02-02": 3,
        "2016-04-11": 3,
        "2025-04-07": 3,
        "2013-03-01": 3,
        "2002-03-01": -1,
        "2015-11-09": 3,
        "2010-09-01": 3,
        "2026-02-02": 3,
        "2007-06-01": 3,
        "2004-10-01": 3,
        "2017-06-12": 3,
        "2026-05-11": 3,
        "2005-10-01": 3,
        "2002-12-01": 3,
        "2002-10-01": 3,
        "2005-04-01": 3,
        "2006-09-01": 3,
        "2015-01-01": 3,
        "2003-07-08": 3,
        "2017-09-18": 3,
        "2010-03-01": 3,
        "2002-07-01": 3,
        "2018-05-21": 3,
        "2014-01-01": 3,
        "2023-09-23": 3,
        "2015-07-16": 3,
        "2012-09-01": 3,
        "2021-07-01": 3,
        "2003-05-08": 3,
        "2018-09-17": 3,
        "2019-10-14": 3,
        "2018-02-05": 3,
        "2002-05-01": 3,
        "2014-07-14": 3,
        "2016-08-29": 3,
        "2011-03-01": 3,
        "2007-09-01": 3
      },
      "md_banlist_data": {
        "2025-05-09": 3,
        "2023-07-13": 3,
        "2024-11-01": 3,
        "2026-01-08": 3,
        "2025-03-06": 3,
        "2023-01-10": 3,
        "2023-05-10": 3,
        "2023-12-05": 3,
        "2025-02-06": 3,
        "2024-03-08": 3,
        "2026-04-01": 3,
        "2023-10-10": 3,
        "2022-05-09": 3,
        "2024-04-11": 3,
        "2022-10-28": 3,
        "2025-08-04": 3,
        "2024-07-29": 3,
        "2024-01-10": 3,
        "2025-06-01": 3,
        "2024-06-07": 3,
        "2025-07-04": 3,
        "2026-02-05": 3,
        "2026-05-07": 3,
        "2022-08-31": 3,
        "2023-04-10": 3,
        "2023-05-01": 3,
        "2024-02-07": 3,
        "2023-07-01": 3,
        "2025-10-08": 3,
        "2024-08-08": 3,
        "2023-02-06": 3,
        "2022-12-01": 3,
        "2023-11-09": 3,
        "2023-06-08": 3,
        "2025-01-09": 3,
        "2026-03-01": 3,
        "2024-12-06": 3,
        "2025-11-07": 3,
        "2023-08-10": 3,
        "2024-09-12": 3,
        "2023-03-01": 3,
        "2025-12-05": 3,
        "2023-03-09": 3,
        "2023-09-01": 3,
        "2022-07-11": 3,
        "2022-01-19": 3,
        "2025-09-10": 3,
        "2024-05-01": 3,
        "2025-06-24": 3,
        "2024-10-10": 3,
        "2024-11-07": 3,
        "2025-04-10": 3,
        "2022-09-30": 3,
        "2024-10-28": 3,
        "2022-09-16": 3,
        "2025-03-28": 3,
        "2023-02-14": 3,
        "2023-10-30": 3,
        "2024-07-11": 3
      },
      "genesys_points": 0
    }
  ],
  "total": 1
}
```

## Legal

Yu-Gi-Oh! is a trademark of Konami Group Corporation and Shueisha Inc. Card data, artwork, and related content are owned by Konami Group Corporation, Shueisha Inc., and Nihon Ad Systems (NAS). This data dump is an unofficial fan project and is not affiliated with or endorsed by any of these entities.

*R.I.P. Kazuki Takahashi (1961–2022). Thank you for creating the game we all love.*
