"""Real estate agencies of a few departments (activity 68.31Z, active), from
the Annuaire des entreprises (recherche-entreprises.api.gouv.fr, INSEE
Sirene and RNE open data): the starting list of the email campaign.

The open data has no email addresses: the CSV has an empty « email » column
to fill from each agency's website (or a compliant B2B file) before the
import into Brevo. Officers' names are public (RNE) and only used to greet
the manager of the agency.

  python scripts/campaign/agencies.py --dep 59 62 --out agences.csv [--prefix 590 591 595]
"""
import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterator, List, Optional

URL = "https://recherche-entreprises.api.gouv.fr/search"
COLUMNS = ["email", "agence", "civilite_nom", "adresse", "code_postal", "ville", "code_insee", "siren",
           "etablissements", "categorie", "date_creation"]


def get(params: Dict[str, str]) -> Optional[Dict]:
    for attempt in range(5):
        try:
            req = urllib.request.Request(f"{URL}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "SPREA"})
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                return None
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2 ** attempt)
    return None


def officer(result: Dict) -> str:
    """First natural person among the officers: « M. Dupont » style greeting
    is left to the email; here the name as published."""
    for d in result.get("dirigeants") or []:
        if d.get("type_dirigeant") == "personne physique" and d.get("nom"):
            first = (d.get("prenoms") or "").split(" ")[0].title()
            return f"{first} {d['nom'].title()}".strip()
    return ""


def agencies(dep: str) -> Iterator[Dict]:
    page = 1
    while True:
        data = get({"activite_principale": "68.31Z", "departement": dep, "etat_administratif": "A",
                    "per_page": "25", "page": str(page)})
        if not data:
            return
        for r in data.get("results") or []:
            siege = r.get("siege") or {}
            if siege.get("departement") not in (None, dep):
                continue
            yield {
                "email": "", "agence": r.get("nom_raison_sociale") or r.get("nom_complet"),
                "civilite_nom": officer(r), "adresse": siege.get("adresse"), "code_postal": siege.get("code_postal"),
                "ville": siege.get("libelle_commune"), "code_insee": siege.get("commune"), "siren": r.get("siren"),
                "etablissements": r.get("nombre_etablissements_ouverts"), "categorie": r.get("categorie_entreprise"),
                "date_creation": r.get("date_creation"),
            }
        if page >= (data.get("total_pages") or 0):
            return
        page += 1
        time.sleep(0.2)  # The API allows 7 requests per second


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dep", nargs="+", default=["59", "62"])
    ap.add_argument("--prefix", nargs="*", help="Only these postcode prefixes (e.g. 590 591 595 for the Lille area)")
    ap.add_argument("--out", default="agences.csv")
    args = ap.parse_args()
    rows: List[Dict] = []
    for dep in args.dep:
        for a in agencies(dep):
            if args.prefix and not any((a["code_postal"] or "").startswith(p) for p in args.prefix):
                continue
            rows.append(a)
        print(f"{dep} : {len(rows)} agences au total", flush=True)
    seen = set()
    rows = [r for r in rows if not (r["siren"] in seen or seen.add(r["siren"]))]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} agences écrites dans {args.out}")


if __name__ == "__main__":
    main()
