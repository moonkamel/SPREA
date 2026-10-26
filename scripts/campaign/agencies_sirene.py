"""Real estate agencies of an area (activity 68.31Z, active) from the INSEE
Sirene stock files on data.gouv.fr: same list as agencies.py, without the
Annuaire des entreprises API (unreachable from some hosts, GitHub runners
included). Only the units and establishments whose data is public
(statutDiffusion « O »): those who opposed it are not prospected.

Writes the campaign CSV (same columns as agencies.py) plus « noms » (trade
names and legal name, « | »-separated) and « dirigeant » for an individual
entrepreneur, read by find_emails.py --agencies.

  python scripts/campaign/agencies_sirene.py --epci 200093201 --out agences.csv
  python scripts/campaign/agencies_sirene.py --dep 59 62 --out agences.csv
"""
import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.request
import zipfile
from typing import Dict, List, Optional, Set

DATASET = "https://www.data.gouv.fr/api/1/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret/"
GEO_EPCI = "https://geo.api.gouv.fr/epcis/{}/communes?fields=code,nom"
NAF = "68.31Z"
COLUMNS = ["email", "agence", "civilite_nom", "adresse", "code_postal", "ville", "code_insee", "siren",
           "etablissements", "categorie", "date_creation", "noms", "dirigeant"]
csv.field_size_limit(10 ** 7)


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "SPREA"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read())


def stock_url(name: str) -> str:
    """URL of the current zip of a stock file (StockEtablissement, StockUniteLegale)."""
    for r in fetch_json(DATASET)["resources"]:
        title = (r.get("title") or "") + " " + (r.get("url") or "")
        if name in title and "Historique" not in title and "Liens" not in title and (r.get("url") or "").endswith(".zip"):
            return r["url"]
    sys.exit(f"{name} introuvable dans le jeu de données Sirene")


def download(url: str, path: str) -> str:
    if not os.path.exists(path):
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "SPREA"})
        with urllib.request.urlopen(req, timeout=120) as res, open(path, "wb") as f:
            while chunk := res.read(1 << 20):
                f.write(chunk)
        print(f"{path} : {os.path.getsize(path) >> 20} Mo en {time.time() - t0:.0f} s", flush=True)
    return path


def rows(zip_path: str):
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as raw:
            yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))


def address(e: Dict) -> str:
    parts = [e.get("numeroVoieEtablissement"), e.get("indiceRepetitionEtablissement"),
             e.get("typeVoieEtablissement"), e.get("libelleVoieEtablissement")]
    return " ".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dep", nargs="*", default=[])
    ap.add_argument("--epci", help="Only the towns of this intercommunality (SIREN, e.g. 200093201 for the MEL)")
    ap.add_argument("--out", default="agences.csv")
    ap.add_argument("--workdir", default=".")
    args = ap.parse_args()
    towns: Optional[Set[str]] = None
    if args.epci:
        towns = {t["code"] for t in fetch_json(GEO_EPCI.format(args.epci))}
        print(f"{len(towns)} communes dans l'intercommunalité {args.epci}", flush=True)
    if not towns and not args.dep:
        sys.exit("--epci ou --dep requis")

    # Establishments: one per SIREN, the head office when it is in the area
    found: Dict[str, Dict] = {}
    count: Dict[str, int] = {}
    for e in rows(download(stock_url("StockEtablissement"), os.path.join(args.workdir, "etab.zip"))):
        if e.get("activitePrincipaleEtablissement") != NAF or e.get("etatAdministratifEtablissement") != "A":
            continue
        town = e.get("codeCommuneEtablissement") or ""
        if towns is not None and town not in towns:
            continue
        if towns is None and not any(town.startswith(d) for d in args.dep):
            continue
        if e.get("statutDiffusionEtablissement") != "O":
            continue
        siren = e["siren"]
        count[siren] = count.get(siren, 0) + 1
        if siren not in found or e.get("etablissementSiege") == "true":
            found[siren] = e
    print(f"{len(found)} agences (SIREN) dans la zone", flush=True)

    units: Dict[str, Dict] = {}
    for u in rows(download(stock_url("StockUniteLegale"), os.path.join(args.workdir, "ul.zip"))):
        if u["siren"] in found:
            units[u["siren"]] = u

    out: List[Dict] = []
    for siren, e in found.items():
        u = units.get(siren)
        if not u or u.get("statutDiffusionUniteLegale") != "O" or u.get("etatAdministratifUniteLegale") != "A":
            continue
        person = " ".join(p for p in (u.get("prenomUsuelUniteLegale") or u.get("prenom1UniteLegale"),
                                      u.get("nomUsageUniteLegale") or u.get("nomUniteLegale")) if p).title()
        legal = u.get("denominationUniteLegale") or person
        trade = [e.get("enseigne1Etablissement"), e.get("denominationUsuelleEtablissement"),
                 u.get("denominationUsuelle1UniteLegale"), u.get("sigleUniteLegale")]
        names = [n for n in dict.fromkeys([*(t for t in trade if t), legal]) if n]
        out.append({
            "email": "", "agence": names[0], "civilite_nom": person if not u.get("denominationUniteLegale") else "",
            "adresse": address(e), "code_postal": e.get("codePostalEtablissement"),
            "ville": e.get("libelleCommuneEtablissement"), "code_insee": e.get("codeCommuneEtablissement"),
            "siren": siren, "etablissements": count[siren], "categorie": u.get("categorieEntrepriseUniteLegale"),
            "date_creation": u.get("dateCreationUniteLegale"), "noms": " | ".join(names),
            "dirigeant": person if not u.get("denominationUniteLegale") else "",
        })
    # Most recent first (the email search covers the first rows only)
    out.sort(key=lambda r: r["date_creation"] or "", reverse=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} agences écrites dans {args.out} (diffusion publique uniquement)", flush=True)


if __name__ == "__main__":
    main()
