"""Safti advisors from the public « trouver un conseiller » directory
(/trouver-un-conseiller?page=N, allowed by the site's robots.txt). The pages
show no email: the address is built from the first and last names of the page
data, in the network's prenom.nom format (hyphens kept: jean-baptiste.bouju).
Names that do not give one sure address (a space or an apostrophe in a name,
a profile with a number for homonyms) are skipped rather than guessed. Writes
rows in the prospects_a_contacter.csv format.

  python scripts/campaign/safti_directory.py --pages 182 --out safti.csv
  python scripts/campaign/safti_directory.py --files page1.html page2.html --out safti.csv   # saved pages
"""
import argparse
import csv
import re
import sys
import time
import unicodedata
import urllib.request
from typing import Dict, Optional

BASE = "https://www.safti.fr"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
COLUMNS = ["agence", "ville", "email", "email_type", "source_url", "adresse", "code_postal", "siren",
           "date_creation", "source"]
# One advisor of the page data (embedded JSON, quotes escaped or not)
AGENT = re.compile(r'"lastName":"([^"]*)","firstName":"([^"]*)","postCode":"([^"]*)","city":"([^"]*)"')
SLUG = re.compile(r'"slug":"([a-z0-9-]+)"')
PART = re.compile(r"^[a-z]+(?:-[a-z]+)*$")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="replace")


def ascii_part(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"\s*-\s*", "-", s)


def address(first: str, last: str) -> Optional[str]:
    """prenom.nom@safti.fr, or None when the name allows several spellings."""
    f, l = ascii_part(first), ascii_part(last)
    if not PART.match(f) or not PART.match(l):
        return None
    return f"{f}.{l}@safti.fr"


def nice_name(s: str) -> str:
    return "-".join(w.capitalize() for w in s.strip().split("-")) if s.isupper() else s.strip()


def parse(text: str, rows: Dict[str, dict], skipped: set) -> int:
    text = text.replace('\\"', '"')
    new = 0
    for m in AGENT.finditer(text):
        s = SLUG.search(text, m.end(), m.end() + 4000)
        if not s:
            continue
        slug = s.group(1)
        if slug in rows or slug in skipped:
            continue
        last, first, cp, city = (g.strip() for g in m.groups())
        email = address(first, last) if not re.search(r"\d", slug) else None
        if not email:
            skipped.add(slug)
            continue
        rows[slug] = {"agence": f"{nice_name(first)} {nice_name(last)}", "ville": city.title(), "email": email,
                      "email_type": "déduit (format Safti)", "source_url": f"{BASE}/votre-conseiller-safti/{slug}",
                      "adresse": "", "code_postal": cp, "siren": "", "date_creation": "",
                      "source": "annuaire Safti (adresse déduite)"}
        new += 1
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=182)
    ap.add_argument("--files", nargs="*", help="saved directory pages instead of the site")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows: Dict[str, dict] = {}
    skipped: set = set()
    if args.files:
        for path in args.files:
            n = parse(open(path, encoding="utf-8", errors="replace").read(), rows, skipped)
            print(f"{path} : {n} nouveaux", flush=True)
    else:
        empty = 0
        for page in range(1, args.pages + 1):
            try:
                text = fetch(f"{BASE}/trouver-un-conseiller?page={page}")
            except Exception as e:  # noqa: BLE001 - a refusal or the end: keep what was read
                print(f"page {page} : {e}", file=sys.stderr, flush=True)
                break
            n = parse(text, rows, skipped)
            print(f"page {page} : {n} nouveaux", flush=True)
            empty = empty + 1 if not n else 0
            if empty >= 3:
                break
            time.sleep(2)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        for slug in sorted(rows):
            w.writerow(rows[slug])
    print(f"{len(rows)} conseillers écrits dans {args.out}, {len(skipped)} fiches ignorées (nom ambigu) : "
          f"{', '.join(sorted(skipped))}", flush=True)


if __name__ == "__main__":
    main()
