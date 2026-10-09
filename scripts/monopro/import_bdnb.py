"""Whole buildings held by a single owner (monopropriétés), from the BDNB
open data (CSTB, Licence Ouverte 2.0), loaded into Supabase for the
prospection map (supabase/migrations/011_monopro.sql).

  python scripts/monopro/import_bdnb.py --dep 59             # import one department
  python scripts/monopro/import_bdnb.py --dep 59 --dry-run   # counts only

A building is kept when it has at least MIN_LOG dwellings, is not registered
as a copropriété, is not social housing (RPLS) and is held by a private
company: an SCI or another commercial or civil company (owner_share = units
held / dwellings). Public bodies, social landlords (OPH, SA d'HLM, ESH...),
associations, foundations, mutual and pension funds, SCPI and buildings
without an identified company owner are left out.

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (except with --dry-run), and
pyproj to convert the building outlines (Lambert 93 or overseas CRS) to GPS.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import date
from typing import Dict, Iterator, List, Optional, Tuple

MILLESIME = os.environ.get("BDNB_MILLESIME", "2026-02-a")
URL = ("https://open-data.s3.fr-par.scw.cloud/bdnb_millesime_{m}/millesime_{m}_dep{d}/"
       "open_data_millesime_{m}_dep{d}_csv.zip")
MIN_LOG = 3
# A company is the single owner when it holds most units of the building
MIN_SHARE = 0.8
# Legal forms of private companies (BDNB "forme_juridique"): SCI and equivalents
PRIVATE_FORMS = {"SCI", "SC", "SARL", "EURL", "SAS", "SASU", "SA", "SNC", "SCA", "SCS", "STE", "SELARL", "SELAS"}
# Social landlords and public or non-profit bodies registered as companies (SA
# d'HLM, ESH, SPL...): left out by name
EXCLUDED_NAME = re.compile(
    r"HABITAT|HABITATION|H\.?L\.?M|LOYER MODERE|LOGEMENT SOCIAL|OFFICE PUBLIC|\bOPH\b|\bESH\b|\bSPLA?\b|\bSEM\b|SAEM|ECONOMIE MIXTE|PUBLIQUE LOCALE|AMENAGEMENT|"
    r"VILOGIA|NOREVIE|ARCADE|MAISONS ET CITES|CLESENCE|AXENTIA|LOGIS METROPOLE|PARTENORD|PROMOCIL|TISSERIN|SIGH|"
    r"IMMOBILIERE GRAND HAINAUT|COTTAGE SOCIAL|\bICF\b|CDC HABITAT|\b3F\b|IN'?LI\b|ACTION LOGEMENT|SEQENS|BATIGERE|"
    r"ERILIA|ADOMA|SOLIHA|LOGEMENT INTERMEDIAIRE|FABRIQUE DES QUARTIERS|SNCF|DIOCESAIN|CONGREGATION|MUTUELLE|"
    r"CAISSE|ETABLISSEMENT PUBLIC|FONCIER DE")
BATCH = 1000
LABELS = "ABCDEFG"

csv.field_size_limit(50_000_000)


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def rows(z: zipfile.ZipFile, table: str) -> Iterator[Dict[str, str]]:
    name = f"csv/{table}.csv"
    if name not in z.namelist():
        log(f"{table}: absent")
        return
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter=";")


def _int(v: Optional[str]) -> Optional[int]:
    try:
        return int(float(v)) if v not in (None, "") else None
    except ValueError:
        return None


def _date(v: Optional[str]) -> Optional[str]:
    m = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})", v or "")
    return f"{m[1]}-{m[2]}-{m[3]}" if m else None


def is_public(siren: str) -> bool:
    """State, local authorities and public bodies have a SIREN starting with 1 or 2."""
    return siren[:1] in ("1", "2")


def centroid(wkt: str) -> Optional[Tuple[float, float]]:
    """Average of the vertices of the outline: enough to place a marker."""
    pts = re.findall(r"(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)", wkt or "")
    if not pts:
        return None
    xs = [float(x) for x, _ in pts]
    ys = [float(y) for _, y in pts]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def is_private_company(owner: Dict) -> bool:
    """SCI or another private company, not a social landlord or a public body."""
    return (not is_public(owner["siren"]) and (owner.get("legal_form") or "").upper() in PRIVATE_FORMS
            and not EXCLUDED_NAME.search((owner.get("name") or "").upper()))


def select_owner(holdings: List[Tuple[str, int]], nb_log: int, owners: Dict[str, Dict]) -> Tuple[str, Optional[str], Optional[float]]:
    """('company', siren, share) | ('unknown', None, None) | ('skip', None, None)."""
    known = [(owners[p], n) for p, n in holdings if p in owners]
    if not known:
        return "unknown", None, None
    if not all(is_private_company(o) for o, _ in known):
        return "skip", None, None
    owner, units = max(known, key=lambda t: t[1])
    share = units / nb_log if nb_log else 0
    if share < MIN_SHARE:
        return "skip", None, None  # Several owners: most likely an unregistered copropriété
    return "company", owner["siren"], round(min(share, 9.99), 2)


def build(z: zipfile.ZipFile, dep: str, today: str) -> Tuple[List[Dict], Dict[str, Dict], Counter]:
    stats = Counter()
    candidates: Dict[str, Dict] = {}
    for r in rows(z, "batiment_groupe_ffo_bat"):
        n = _int(r.get("nb_log"))
        if n and n >= MIN_LOG:
            candidates[r["batiment_groupe_id"]] = {"nb_log": n, "levels": _int(r.get("nb_niveau")),
                                                    "year_built": _int(r.get("annee_construction"))}
    stats["buildings_3_plus_dwellings"] = len(candidates)

    for table, reason in (("batiment_groupe_rnc", "in_copro_registry"), ("batiment_groupe_rpls", "social_housing")):
        for r in rows(z, table):
            if candidates.pop(r["batiment_groupe_id"], None):
                stats[reason] += 1

    owners: Dict[str, Dict] = {}
    for r in rows(z, "proprietaire"):
        siren = (r.get("siren") or "").strip()
        if re.fullmatch(r"\d{9}", siren):
            owners[r["personne_id"]] = {"siren": siren, "name": (r.get("denomination") or "").strip()[:200] or None,
                                        "legal_form": (r.get("forme_juridique") or "").strip()[:40] or None,
                                        "postcode": (r.get("code_postal") or "").strip()[:10] or None,
                                        "city": (r.get("libelle_commune") or "").strip()[:100] or None}
    holdings: Dict[str, List[Tuple[str, int]]] = {}
    for r in rows(z, "rel_batiment_groupe_proprietaire"):
        if r["batiment_groupe_id"] in candidates:
            holdings.setdefault(r["batiment_groupe_id"], []).append((r["personne_id"], _int(r.get("nb_locaux_open")) or 0))

    used: Dict[str, Dict] = {}
    for bid in list(candidates):
        kind, siren, share = select_owner(holdings.get(bid, []), candidates[bid]["nb_log"], owners)
        if kind != "company":
            # Only buildings held by a private company are kept
            del candidates[bid]
            stats["public_or_shared_owner" if kind == "skip" else "owner_unknown"] += 1
            continue
        candidates[bid].update({"owner_siren": siren, "owner_share": share})
        stats["owner_company"] += 1
        if siren:
            used[siren] = next(o for o in owners.values() if o["siren"] == siren)

    for r in rows(z, "batiment_groupe_adresse"):
        c = candidates.get(r["batiment_groupe_id"])
        if c:
            c["address"] = (r.get("libelle_adr_principale_ban") or "").strip()[:200] or None
    for r in rows(z, "batiment_groupe_dpe_representatif_logement"):
        c = candidates.get(r["batiment_groupe_id"])
        label = (r.get("classe_bilan_dpe") or "").strip().upper()
        if c and len(label) == 1 and label in LABELS:
            c["dpe_label"] = label
            c["dpe_date"] = _date(r.get("date_etablissement_dpe"))
    stat_cols = None
    for r in rows(z, "batiment_groupe_dpe_statistique_logement"):
        if stat_cols is None:
            stat_cols = {l: f"nb_classe_bilan_dpe_{l.lower()}" for l in LABELS if f"nb_classe_bilan_dpe_{l.lower()}" in r}
            log("dpe statistics columns:", list(r.keys())[:20])
        c = candidates.get(r["batiment_groupe_id"])
        if c and stat_cols:
            counts = {l: _int(r.get(col)) or 0 for l, col in stat_cols.items()}
            c["dpe_count"] = sum(counts.values()) or None
            c["dpe_fg"] = (counts.get("F", 0) + counts.get("G", 0)) or None
    for r in rows(z, "batiment_groupe_dvf_open_representatif"):
        c = candidates.get(r["batiment_groupe_id"])
        if c:
            c["last_sale_date"] = _date(r.get("date_mutation"))
            c["last_sale_price"] = _int(r.get("valeur_fonciere"))
            c["last_sale_units"] = _int(r.get("nb_locaux_mutee_mutation"))

    from pyproj import CRS, Transformer
    prj = z.read("csv/batiment_groupe.prj").decode("utf-8", "replace")
    to_gps = Transformer.from_crs(CRS.from_wkt(prj), "EPSG:4326", always_xy=True)
    for r in rows(z, "batiment_groupe"):
        c = candidates.get(r["batiment_groupe_id"])
        if c:
            c["insee"] = (r.get("code_commune_insee") or "").strip()[:5] or None
            xy = centroid(r.get("geom_groupe", ""))
            if xy:
                lon, lat = to_gps.transform(*xy)
                c["lat"], c["lon"] = round(lat, 6), round(lon, 6)

    out = []
    keys = ["insee", "address", "lat", "lon", "nb_log", "levels", "year_built", "owner_siren", "owner_share",
            "dpe_label", "dpe_date", "dpe_count", "dpe_fg", "last_sale_date", "last_sale_price", "last_sale_units"]
    for bid, c in candidates.items():
        if c.get("lat") is None:
            stats["no_position"] += 1
            continue
        out.append({"id": bid, "dep": dep, **{k: c.get(k) for k in keys}, "imported_on": today})
    stats["kept"] = len(out)
    stats["companies"] = len(used)
    return out, {s: {**o, "siren": s, "imported_on": today} for s, o in used.items()}, stats


class Rest:
    def __init__(self, url: str, key: str):
        self.base = f"{url.rstrip('/')}/rest/v1"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):
            self.headers["Authorization"] = f"Bearer {key}"

    def call(self, method: str, path: str, body: Optional[bytes] = None, prefer: str = "return=minimal"):
        for attempt in range(5):
            req = urllib.request.Request(f"{self.base}/{path}", data=body, method=method,
                                         headers={**self.headers, "Prefer": prefer})
            try:
                with urllib.request.urlopen(req, timeout=120) as res:
                    return res.read()
            except urllib.error.HTTPError as e:
                if e.code < 500 or attempt == 4:
                    raise RuntimeError(f"{method} {path.split('?')[0]} failed: {e.code} {e.read()[:300]!r}")
            except urllib.error.URLError:
                if attempt == 4:
                    raise
            time.sleep(2 ** attempt)

    def upsert(self, table: str, items: List[Dict]):
        for i in range(0, len(items), BATCH):
            self.call("POST", f"{table}?on_conflict={'siren' if table == 'monopro_owners' else 'id'}",
                      json.dumps(items[i:i + BATCH]).encode(), "resolution=merge-duplicates,return=minimal")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dep", required=True)
    ap.add_argument("--file", help="Local zip instead of the BDNB download")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dep = args.dep.upper()
    today = date.today().isoformat()

    path = args.file
    if not path:
        path = f"bdnb_{dep}.zip"
        log(f"Downloading {URL.format(m=MILLESIME, d=dep.lower())}")
        urllib.request.urlretrieve(URL.format(m=MILLESIME, d=dep.lower()), path)
    with zipfile.ZipFile(path) as z:
        buildings, owners, stats = build(z, dep, today)
    log(json.dumps(stats, indent=1))
    log(f"~{len(json.dumps(buildings)) // 1024} KB of buildings, {len(json.dumps(list(owners.values()))) // 1024} KB of owners")
    if args.dry_run:
        for b in buildings[:3]:
            log({k: b[k] for k in ("address", "nb_log", "owner_siren", "dpe_label", "last_sale_date")})
        return

    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    rest = Rest(url, key)
    if not buildings:
        sys.exit(f"No building found for {dep}: nothing changed")
    # The department is replaced as a whole (the selection rules may have changed)
    rest.call("DELETE", f"monopro_buildings?dep=eq.{dep}")
    rest.upsert("monopro_owners", list(owners.values()))
    rest.upsert("monopro_buildings", buildings)
    log(f"{len(buildings)} buildings and {len(owners)} owners loaded for {dep}")


if __name__ == "__main__":
    main()
