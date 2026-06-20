from __future__ import annotations

import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from examdino_data import SUBJECTS


OUT_DIR = Path(__file__).resolve().parents[1] / "data"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "cambridge_subject_sources.json"


def scrape_page(url: str) -> dict[str, str]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.find("h1")
    meta = soup.find("meta", attrs={"name": "description"})
    return {
        "title": title.get_text(" ", strip=True) if title else "",
        "description": meta["content"].strip() if meta and meta.get("content") else "",
        "url": url,
    }


def main() -> None:
    catalog = {}
    for slug, subject in SUBJECTS.items():
        try:
            catalog[slug] = scrape_page(subject.source_url)
        except Exception as exc:  # pragma: no cover
            catalog[slug] = {
                "title": subject.name,
                "description": subject.overview,
                "url": subject.source_url,
                "error": str(exc),
            }
    OUT_FILE.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
