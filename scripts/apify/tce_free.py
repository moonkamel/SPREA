"""Free replacement for the Apify TCE pipeline (tce_pipeline.py): the same CSV, from public
data only, no paid service.

1. Liste des entreprises RGE (ADEME open data): name, SIRET, address, position, phone,
   email, website and the work domains of each qualification -> trades, TCE or not.
2. Annuaire des entreprises (API of the State, no key): officers, NAF, headcount band,
   revenue when published, open or closed. Firms that carry out no works (architects
   71.11Z, design offices, developers, wholesalers) and closed firms are left out.
3. The firm's own website (contact and legal notice pages, mandatory in France): the
   addresses published there, to find a named email rather than contact@.
4. Scores as in tce_pipeline.py (trades, capacity, F/G DPE around the firm).

Every step is cached in --out (JSON), so a run cut short resumes where it stopped.

  python scripts/apify/tce_free.py --deps 02 60 80 --out gratuit          # TCE only
  python scripts/apify/tce_free.py --deps 02 60 80 --out gratuit --all    # every RGE firm
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from typing import Dict, List, Optional

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from tce_pipeline import (COLUMNS, GLOBAL, MIN_TRADES_TCE, best_email, fg_density, score_multi,  # noqa: E402
                          score_proximity)

RGE = "https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines"
ANNUAIRE = "https://recherche-entreprises.api.gouv.fr/search"
UA = {"User-Agent": "SPREA prospection (sprea.app)"}

# Work domains of the RGE list -> trade, by keywords (robust to small changes of wording)
KEYWORDS = [
    ("projet complet", GLOBAL), ("renovation globale", GLOBAL), ("offre globale", GLOBAL), ("audit", None),
    ("isolation", "Isolation"), ("combles", "Isolation"), ("planchers bas", "Isolation"),
    ("fenetre", "Menuiserie"), ("volet", "Menuiserie"), ("porte", "Menuiserie"),
    ("pompe a chaleur", "Chauffage"), ("chaudiere", "Chauffage"), ("poele", "Chauffage"), ("insert", "Chauffage"),
    ("radiateur", "Électricité / chauffage électrique"),
    ("chauffe eau", "Eau chaude sanitaire"), ("solaire", "Eau chaude sanitaire"),
    ("ventilation", "Ventilation"), ("photovolta", "Photovoltaïque"), ("geotherm", "Géothermie"),
]


def plain(text) -> str:
    t = unicodedata.normalize("NFD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t)


def trade_of(domain: str) -> Optional[str]:
    p = plain(domain)
    if "photovolta" in p:
        return "Photovoltaïque"
    if "solaire" in p and "eau" not in p and "chauff" not in p:
        return "Photovoltaïque"
    for key, trade in KEYWORDS:
        if key in p:
            return trade
    return None


def cache(path: str, compute):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    data = compute()
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return data


# --- 1. RGE list -------------------------------------------------------------

def rge_lines(client: httpx.Client, dep: str) -> List[Dict]:
    out, url = [], f"{RGE}?" + urllib.parse.urlencode({"qs": f"code_postal:{dep}*", "size": 2000})
    while url:
        for attempt in range(4):
            try:
                res = client.get(url, timeout=60)
                res.raise_for_status()
                break
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise
                print(f"ADEME : {e}, nouvel essai", flush=True)
                time.sleep(5 * (attempt + 1))
        data = res.json()
        out += data.get("results") or []
        url = data.get("next")
    print(f"  {dep} : {len(out)} lignes RGE", flush=True)
    return out


def firms_from_rge(lines: List[Dict]) -> Dict[str, Dict]:
    firms: Dict[str, Dict] = {}
    for r in lines:
        siret = re.sub(r"\D", "", str(r.get("siret") or ""))
        if len(siret) < 9:
            continue
        f = firms.setdefault(siret[:9], {"siren": siret[:9], "siret": siret, "name": r.get("nom_entreprise") or "",
                                         "address": " ".join(x for x in (r.get("adresse"), r.get("code_postal"), r.get("commune")) if x),
                                         "postcode": str(r.get("code_postal") or ""), "lat": r.get("latitude"),
                                         "lon": r.get("longitude"), "phone": r.get("telephone") or "",
                                         "emails": [], "website": r.get("site_internet") or "", "trades": [], "quals": []})
        if r.get("email") and r["email"] not in f["emails"]:
            f["emails"].append(r["email"])
        f["website"] = f["website"] or r.get("site_internet") or ""
        f["phone"] = f["phone"] or r.get("telephone") or ""
        t = trade_of(r.get("domaine")) or trade_of(r.get("meta_domaine"))
        if t and t not in f["trades"]:
            f["trades"].append(t)
        q = r.get("nom_qualification") or r.get("organisme") or ""
        if q and q not in f["quals"]:
            f["quals"].append(q)
    return firms


def is_tce(f: Dict) -> bool:
    return GLOBAL in f["trades"] or len([t for t in f["trades"] if t != GLOBAL]) >= MIN_TRADES_TCE


# --- 2. Annuaire des entreprises ----------------------------------------------

def annuaire(client: httpx.Client, siren: str) -> Optional[Dict]:
    for attempt in range(6):
        try:
            res = client.get(ANNUAIRE, params={"q": siren, "per_page": 1}, timeout=20)
        except httpx.HTTPError:
            time.sleep(5 * (attempt + 1))
            continue
        if res.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if res.status_code != 200:
            return None
        hits = [h for h in res.json().get("results") or [] if h.get("siren") == siren]
        if not hits:
            return {}
        h = hits[0]
        people = [d for d in h.get("dirigeants") or [] if d.get("type_dirigeant") == "personne physique"]
        boss = next((d for d in people if re.search(r"(?i)g[ée]rant|pr[ée]sident|directeur", d.get("qualite") or "")), None) \
            or (people[0] if people else None)
        director = " ".join(x for x in (((boss or {}).get("prenoms") or "").split(" ")[0].title(),
                                        ((boss or {}).get("nom") or "").title()) if x) if boss else ""
        fin = h.get("finances") or {}
        last = (fin[max(fin)] or {}) if fin else {}
        return {"director": director, "naf": h.get("activite_principale") or "",
                "active": h.get("etat_administratif") == "A", "band": h.get("tranche_effectif_salarie") or "",
                "revenue": last.get("ca"), "legal_name": h.get("nom_raison_sociale") or h.get("nom_complet") or ""}
    return None


def does_works(naf: str) -> bool:
    return not naf or naf.startswith(("41.2", "43."))


# --- 3. Website: contact and legal notice pages ---------------------------------

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SKIP = ("example", "sentry", "wixpress", "domain.", "@2x", ".png", ".jpg", ".webp", "votre", "your")


def site_emails(client: httpx.Client, website: str) -> List[str]:
    if not website:
        return []
    website = website.strip().lstrip("/")
    base = website if website.startswith("http") else f"https://{website}"
    found: List[str] = []
    for path in ("", "/contact", "/mentions-legales", "/mentions-legales/", "/contact/"):
        try:
            res = client.get(urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/")), timeout=8, follow_redirects=True)
        except (httpx.HTTPError, ValueError):  # unreachable site or malformed address
            continue
        if res.status_code != 200 or "html" not in res.headers.get("content-type", ""):
            continue
        for e in EMAIL.findall(res.text):
            e = e.strip(".").lower()
            if not any(s in e for s in SKIP) and e not in found:
                found.append(e)
        if len(found) >= 6:
            break
    return found


# --- 4. Rows --------------------------------------------------------------------

BAND_10 = {"11", "12", "21", "22", "31", "32", "41", "42", "51", "52", "53"}  # 10 salaried staff and more


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deps", nargs="+", default=["02", "60", "80"])
    ap.add_argument("--out", default="gratuit")
    ap.add_argument("--all", action="store_true", help="every RGE firm, not only the TCE ones")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    with httpx.Client(headers=UA) as client:
        lines = []
        for dep in args.deps:
            lines += cache(os.path.join(args.out, f"1_rge_{dep}.json"), lambda d=dep: rge_lines(client, d))
        firms = firms_from_rge(lines)
        kept = {s: f for s, f in firms.items() if args.all or is_tce(f)}
        print(f"{len(firms)} entreprises RGE, {len(kept)} retenues ({'toutes' if args.all else 'tous corps d etat'})", flush=True)

        info_path = os.path.join(args.out, "2_annuaire.json")
        info: Dict[str, Dict] = json.load(open(info_path, encoding="utf-8")) if os.path.exists(info_path) else {}
        todo = [s for s in kept if s not in info]
        for i, s in enumerate(todo, 1):
            try:
                got = annuaire(client, s)
            except Exception as e:  # noqa: BLE001 - one odd record must not stop the department
                print(f"Annuaire illisible pour {s} : {type(e).__name__} {e}", flush=True)
                got = None
            if got is not None:
                info[s] = got
            if i % 50 == 0:
                json.dump(info, open(info_path, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  Annuaire : {i} / {len(todo)}", flush=True)
            time.sleep(0.4)
        json.dump(info, open(info_path, "w", encoding="utf-8"), ensure_ascii=False)

        sites_path = os.path.join(args.out, "3_sites.json")
        sites: Dict[str, List[str]] = json.load(open(sites_path, encoding="utf-8")) if os.path.exists(sites_path) else {}
        for i, (s, f) in enumerate(kept.items(), 1):
            if s not in sites and f.get("website"):
                try:
                    sites[s] = site_emails(client, f["website"])
                except Exception as e:  # noqa: BLE001 - one odd website must not stop the department
                    print(f"Site illisible pour {s} : {type(e).__name__}", flush=True)
                    sites[s] = []
                if i % 50 == 0:
                    json.dump(sites, open(sites_path, "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(sites, open(sites_path, "w", encoding="utf-8"), ensure_ascii=False)

    density: Dict[str, int] = {}
    rows, positions, left = [], [], {"fermée": 0, "sans travaux": 0, "inconnue de l'Annuaire": 0}
    for s, f in kept.items():
        a = info.get(s)
        if a is None or a == {}:
            left["inconnue de l'Annuaire"] += 1
            a = a or {}
        elif not a.get("active", True):
            left["fermée"] += 1
            continue
        elif not does_works(a.get("naf", "")):
            left["sans travaux"] += 1
            continue
        director = a.get("director", "")
        name = f["name"] or a.get("legal_name", "")
        email, status = best_email(f["emails"] + sites.get(s, []), director, name, f.get("website", ""))
        multi = score_multi(f["trades"])
        capa = (2 if a.get("band") in BAND_10 else 0) + (3 if (a.get("revenue") or 0) > 1_000_000 else 0)
        prox = score_proximity(fg_density(f["postcode"], density))
        rows.append({
            "Entreprise_Nom": name, "Entreprise_Type": "TCE" if is_tce(f) else "RGE", "Dirigeant_Nom": director,
            "Email": email, "Email_Statut": status, "Téléphone": f["phone"], "Adresse": f["address"],
            "CodePostal": f["postcode"], "SIRET": f["siret"], "Codes_NAF": a.get("naf", ""),
            "Qualifications_RGE": " | ".join(f["quals"]), "Nb_Corps_Metier": len([t for t in f["trades"] if t != GLOBAL]),
            "Effectif": a.get("band", ""), "CA": a.get("revenue") or "", "Score_Multi_Competence": multi,
            "Score_Capacite_Chantier": capa, "Score_Proximite": prox, "Score_Final": multi + capa + prox,
            "Eco_Artisan_CAPEB": "",
        })
        if f.get("lat") and f.get("lon"):
            positions.append({"siren": s, "latitude": f["lat"], "longitude": f["lon"]})
    rows.sort(key=lambda x: (-x["Score_Final"], x["Entreprise_Nom"]))
    with open(os.path.join(args.out, "prospection_tce_gratuit.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    json.dump(positions, open(os.path.join(args.out, "1a_rge_registre.json"), "w", encoding="utf-8"))
    from collections import Counter
    print(f"\n{len(rows)} entreprises dans le fichier ; écartées : {left}")
    print("Statut des mails :", dict(Counter(r["Email_Statut"] for r in rows)))
    print("Avec dirigeant :", sum(1 for r in rows if r["Dirigeant_Nom"]), "· par département :",
          dict(Counter(r["CodePostal"][:2] for r in rows)))


if __name__ == "__main__":
    main()
