"""iad France advisors of a town, from the public « trouver un conseiller »
directory (allowed by the site's robots.txt). The pages show no email: the
address is deduced from the profile slug, which follows the network's
prenom.nom format (prenom.nom-compose for compound names), e.g.
/conseiller-immobilier/albin.quicampoix -> albin.quicampoix@iadfrance.fr.
Slugs without that shape (no dot, digits for homonyms) are skipped rather than
guessed. Writes rows in the prospects_a_contacter.csv format.

The advisor's town is read from the card (« Lyon (69003) »); --ville and --cp
are the fallback.

  python scripts/campaign/iad_directory.py --town pg-lyon_69 --ville Lyon --cp 69000 --out iad_lyon.csv
  python scripts/campaign/iad_directory.py --town seine-et-marne-77 --ville "Seine-et-Marne" --out iad_77.csv
"""
import argparse
import csv
import re
import sys
import time
import urllib.request
from typing import Dict

BASE = "https://www.iadfrance.fr"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
# Town under the advisor's name on the card: « Lyon (69003) »
TOWN = re.compile(r">\s*([A-ZÀ-Ý][^<>()]{1,50}?)\s*\((\d{5})\)\s*<")
SLUG = re.compile(r"^[a-z]+(?:-[a-z]+)*\.[a-z]+(?:-[a-z]+)*$")
COLUMNS = ["agence", "ville", "email", "email_type", "source_url", "adresse", "code_postal", "siren",
           "date_creation", "source"]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--town", required=True, help="Directory slug, e.g. pg-lyon_69")
    ap.add_argument("--ville", required=True)
    ap.add_argument("--cp", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-pages", type=int, default=30)
    args = ap.parse_args()

    names: Dict[str, str] = {}
    towns: Dict[str, tuple] = {}
    skipped = set()
    for page in range(1, args.max_pages + 1):
        url = f"{BASE}/trouver-un-conseiller/{args.town}" + (f"?page={page}" if page > 1 else "")
        try:
            text = fetch(url)
        except Exception as e:  # noqa: BLE001 - end of the pages or a refusal: keep what was read
            print(f"page {page} : {e}", file=sys.stderr)
            break
        slugs = set(re.findall(r'href="/conseiller-immobilier/([a-z0-9.\-]+)"', text))
        new = 0
        for slug in slugs:
            if slug in names or slug in skipped:
                continue
            if not SLUG.match(slug):
                skipped.add(slug)
                continue
            # The page payload holds « "slug","Full Name" » for each advisor
            m = re.search(re.escape(f'"{slug}","') + r'([^"]{3,80})"', text)
            # (the payload is deduplicated: the next string can be a shared value like « male »)
            name = m.group(1).strip() if m else ""
            names[slug] = name if " " in name else slug.replace(".", " ").title()
            card = text.find(f'href="/conseiller-immobilier/{slug}" class=""')
            t = TOWN.search(text, card, card + 3000) if card >= 0 else None
            if t:
                towns[slug] = (t.group(1).strip(), t.group(2))
            new += 1
        print(f"page {page} : {len(slugs)} fiches, {new} nouvelles", flush=True)
        if not new:
            break
        time.sleep(2)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        for slug, name in sorted(names.items()):
            ville, cp = towns.get(slug, (args.ville, args.cp))
            w.writerow({"agence": name, "ville": ville, "email": f"{slug}@iadfrance.fr",
                        "email_type": "déduit (format iad)", "source_url": f"{BASE}/conseiller-immobilier/{slug}",
                        "adresse": "", "code_postal": cp, "siren": "", "date_creation": "",
                        "source": "annuaire iad (adresse déduite)"})
    print(f"{len(names)} conseillers écrits dans {args.out}, {len(skipped)} fiches ignorées (format ambigu) : "
          f"{', '.join(sorted(skipped))}", flush=True)


if __name__ == "__main__":
    main()
