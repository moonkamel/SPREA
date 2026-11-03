"""Livrable « chantiers » : chaque entreprise TCE du fichier Apify reçoit un
immeuble classé F ou G, détenu par une société, près de chez elle, avec le
lien vers son dossier PDF et un texte d'accroche prêt à l'envoi.

Entrées : le dossier de sortie de tce_pipeline.py (CSV et JSON, branche
apify-tce) et les immeubles en monopropriété de SPREA (Supabase, import BDNB).
Pour chaque immeuble : le dossier de cession de SPREA (surface, travaux,
interdictions de location, à partir des DPE de l'ADEME) et la fiche publique
de la société propriétaire (Annuaire des entreprises : gérant, siège).

Un immeuble est proposé à MAX_PER_BUILDING entreprises au plus : le même
chantier envoyé à toute la région n'a plus de valeur.

  SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \\
  python scripts/apify/tce_chantiers.py --tce tce_hdf --out tce_hdf
"""
import argparse
import asyncio
import csv
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.immeuble import ademe_rows  # noqa: E402
from api.monopro import SPREA_AGENCY, fetch_company, share_token  # noqa: E402
from api.monopro_report import build_dossier  # noqa: E402

SITE = "https://sprea.app"
DEPARTMENTS = ["02", "59", "60", "62", "80"]
MAX_KM = 40           # au-delà, un chantier n'est plus dans la zone d'une entreprise
MAX_PER_BUILDING = 2  # entreprises à qui le même immeuble est proposé
COLUMNS = ["Score", "Entreprise", "Dirigeant", "Email", "Email_Statut", "Téléphone", "Distance_km",
           "Immeuble_Adresse", "Logements", "Surface_m2", "DPE", "Travaux_min", "Travaux_max",
           "SCI_Nom", "SCI_SIREN", "SCI_Gerant", "SCI_Siege", "Lien_Dossier", "Accroche"]


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def euros(v: float) -> str:
    return f"{round(v / 1000) * 1000:,.0f} €".replace(",", " ")


# --- Entreprises TCE : contacts (CSV) et position (JSON des Actors) ---------

def company_positions(tce_dir: str) -> Dict[str, Tuple[float, float]]:
    """Position de l'établissement dans les Hauts-de-France, par SIREN : registre
    RGE, puis fiche dirigeant, puis établissement trouvé par la recherche NAF."""
    pos: Dict[str, Tuple[float, float]] = {}

    def add(siren, lat, lon):
        try:
            if siren and lat and lon and str(siren)[:9] not in pos:
                pos[str(siren)[:9]] = (float(lat), float(lon))
        except (TypeError, ValueError):
            pass

    def load(name):
        path = os.path.join(tce_dir, name + ".json")
        return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    for r in load("1a_rge_registre"):
        add(r.get("siren") or r.get("siret"), r.get("latitude"), r.get("longitude"))
    for name in ("2_dirigeants", "2_dirigeants_suite"):
        for r in load(name):
            add(r.get("siren") or r.get("siret"), r.get("latitude"), r.get("longitude"))
    for name in ("1b_entreprises_naf", "1b_entreprises_tce_sirens"):
        for c in load(name):
            places = [e for e in c.get("matchingEstablishments") or [] if isinstance(e, dict)]
            hq = c.get("headquarters") or {}
            if hq.get("department") in DEPARTMENTS:
                places.append(hq)
            for e in places:
                if str(e.get("department") or e.get("postalCode") or "")[:2] in DEPARTMENTS:
                    add(c.get("siren"), e.get("latitude"), e.get("longitude"))
                    break
    return pos


# --- Immeubles : Supabase, dossier SPREA, propriétaire ----------------------

async def load_buildings(client: httpx.AsyncClient) -> List[Dict]:
    url, key = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    out, offset = [], 0
    while True:
        res = await client.get(f"{url}/rest/v1/monopro_buildings", headers=headers, params={
            "select": "*", "dep": f"in.({','.join(DEPARTMENTS)})", "dpe_label": "in.(F,G)",
            "owner_siren": "not.is.null", "order": "id", "limit": 1000, "offset": offset})
        res.raise_for_status()
        page = res.json()
        out += page
        if len(page) < 1000:
            break
        offset += 1000
    sirens = sorted({b["owner_siren"] for b in out})
    owners: Dict[str, Dict] = {}
    for i in range(0, len(sirens), 200):
        res = await client.get(f"{url}/rest/v1/monopro_owners", headers=headers,
                               params={"select": "*", "siren": f"in.({','.join(sirens[i:i + 200])})"})
        res.raise_for_status()
        owners.update({o["siren"]: o for o in res.json()})
    for b in out:
        b["_owner"] = owners.get(b["owner_siren"])
    return out


def officer(company: Optional[Dict]) -> str:
    """Gérant de la société propriétaire (une personne si possible)."""
    officers = (company or {}).get("officers") or []
    person = next((o for o in officers if not o.get("company")), None) or (officers[0] if officers else None)
    if not person:
        return ""
    return f"{person['name']} ({person['role']})" if person.get("role") else person["name"]


async def building_facts(client: httpx.AsyncClient, b: Dict) -> Dict:
    """Ce que dit le dossier SPREA de l'immeuble, sans les prix (inutiles ici)."""
    rows: List[Dict] = []
    try:
        rows = await ademe_rows(client, {"geo_distance": f"{b['lon']},{b['lat']},30", "size": "300"})
    except httpx.HTTPError:
        pass
    company = await fetch_company(b["owner_siren"])
    d = build_dossier(b, b.get("_owner"), company, 0, rows, None, SPREA_AGENCY)
    owner = b.get("_owner") or {}
    works = d.get("works") or {}
    token = share_token(b["id"])
    return {
        "id": b["id"], "address": b.get("address"), "lat": b["lat"], "lon": b["lon"], "nb_log": b["nb_log"],
        "label": d.get("label") or b.get("dpe_label"), "worst": d.get("worst"), "shab": d.get("shab"),
        "works_low": works.get("low"), "works_high": works.get("high"),
        "sci_name": (company or {}).get("name") or owner.get("name") or "",
        "sci_siren": b["owner_siren"], "sci_officer": officer(company),
        "sci_office": (company or {}).get("address") or " ".join(x for x in (owner.get("postcode"), owner.get("city")) if x),
        "sci_active": (company or {}).get("active", True),
        "link": f"{SITE}/api/monopro/{b['id']}/dossier/partage?t={token}" if token else "",
    }


# --- Rapprochement et texte -------------------------------------------------

def building_priority(f: Dict) -> float:
    """0 à 1 : classe G avant F, grande surface avant petite."""
    cls = 1.0 if (f.get("worst") or f.get("label")) == "G" else 0.75
    size = min(1.0, (f.get("shab") or 0) / 800)
    return 0.6 * cls + 0.4 * size


def score(tce_score: float, f: Dict, distance: float) -> float:
    """Score de priorité sur 10 : l'entreprise (45 %), l'immeuble (35 %), la distance (20 %)."""
    return round(10 * (0.45 * min(tce_score, 15) / 15 + 0.35 * building_priority(f)
                       + 0.20 * max(0.0, 1 - distance / MAX_KM)), 1)


def hook(director: str, f: Dict, distance: float) -> str:
    """Texte d'accroche : uniquement des faits du dossier, sans promesse sur le propriétaire."""
    hello = f"Bonjour {director.split(' (')[0]}," if director else "Bonjour,"
    size = f"environ {f['shab']:,} m²".replace(",", " ") if f.get("shab") else f"{f['nb_log']} logements"
    worst = f.get("worst") or f.get("label")
    ban = ("Classé G, ses logements ne peuvent plus être proposés à un nouveau locataire depuis le 1er janvier 2025."
           if worst == "G" else
           "Classé F, ses logements ne pourront plus être proposés à un nouveau locataire à partir du 1er janvier 2028.")
    works = (f" Le dossier chiffre la rénovation énergétique entre {euros(f['works_low'])} et {euros(f['works_high'])}."
             if f.get("works_low") and f.get("works_high") else "")
    return (f"{hello} un immeuble de {f['nb_log']} logements ({size}, classé {f.get('label')}) se trouve à "
            f"{distance:.0f} km de votre entreprise, au {f.get('address')}. Il appartient à la société "
            f"{f['sci_name']} (SIREN {f['sci_siren']}). {ban}{works} Le dossier complet : {f['link']}")


def match(tce_rows: List[Dict], positions: Dict[str, Tuple[float, float]], facts: List[Dict]) -> List[Dict]:
    """Chaque entreprise, par score décroissant, prend le meilleur immeuble à moins de MAX_KM
    encore proposé à moins de MAX_PER_BUILDING entreprises."""
    used: Dict[str, int] = {}
    out = []
    ordered = sorted(tce_rows, key=lambda r: -float(r.get("Score_Final") or 0))
    for r in ordered:
        p = positions.get(str(r.get("SIRET", ""))[:9])
        if not p:
            continue
        best = None
        for f in facts:
            if used.get(f["id"], 0) >= MAX_PER_BUILDING or not f.get("sci_active", True):
                continue
            d = km(p[0], p[1], f["lat"], f["lon"])
            if d > MAX_KM:
                continue
            s = score(float(r.get("Score_Final") or 0), f, d)
            if not best or s > best[0]:
                best = (s, f, d)
        if not best:
            continue
        s, f, d = best
        used[f["id"]] = used.get(f["id"], 0) + 1
        director = r.get("Dirigeant_Nom", "")
        out.append({
            "Score": s, "Entreprise": r.get("Entreprise_Nom"), "Dirigeant": director, "Email": r.get("Email"),
            "Email_Statut": r.get("Email_Statut", ""), "Téléphone": r.get("Téléphone"), "Distance_km": round(d, 1),
            "Immeuble_Adresse": f.get("address"), "Logements": f["nb_log"], "Surface_m2": f.get("shab") or "",
            "DPE": f.get("label"), "Travaux_min": f.get("works_low") or "", "Travaux_max": f.get("works_high") or "",
            "SCI_Nom": f["sci_name"], "SCI_SIREN": f["sci_siren"], "SCI_Gerant": f["sci_officer"],
            "SCI_Siege": f["sci_office"], "Lien_Dossier": f["link"], "Accroche": hook(director, f, d),
        })
    out.sort(key=lambda x: -x["Score"])
    return out


async def main_async(args):
    rows = list(csv.DictReader(open(os.path.join(args.tce, "prospection_tce_hauts_de_france.csv"), encoding="utf-8-sig"),
                               delimiter=";"))
    positions = company_positions(args.tce)
    cache_path = os.path.join(args.out, "4_immeubles_fg.json")
    async with httpx.AsyncClient(timeout=30) as client:
        if os.path.exists(cache_path):
            facts = json.load(open(cache_path, encoding="utf-8"))
        else:
            buildings = await load_buildings(client)
            print(f"{len(buildings)} immeubles F/G détenus par une société dans les Hauts-de-France")
            facts = []
            for i, b in enumerate(buildings):
                facts.append(await building_facts(client, b))
                if i % 50 == 49:
                    print(f"  {i + 1} dossiers calculés", flush=True)
                await asyncio.sleep(0.15)  # Annuaire des entreprises : quelques appels par seconde
            json.dump(facts, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        # Un lien vérifié de bout en bout : le site doit ouvrir le PDF signé
        sample = next((f["link"] for f in facts if f.get("link")), None)
        if sample:
            res = await client.get(sample, timeout=90)
            print(f"Lien de dossier testé : HTTP {res.status_code}, {'PDF' if res.content[:4] == b'%PDF' else 'pas un PDF'}")
    out = match(rows, positions, facts)
    path = os.path.join(args.out, "prospection_TCE_chantiers.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(out)
    located = sum(1 for r in rows if str(r.get("SIRET", ""))[:9] in positions)
    print(f"{len(rows)} entreprises TCE, {located} localisées, {len(out)} avec un chantier à moins de {MAX_KM} km "
          f"-> {path}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tce", default="tce_hdf", help="dossier de sortie de tce_pipeline.py")
    ap.add_argument("--out", default="tce_hdf")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
