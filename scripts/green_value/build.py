"""Measures the "valeur verte": the price gap between DPE classes, from real sales.

Two steps, run by .github/workflows/green-value.yml:

  extract --dep 59 --out matched_59.csv.gz
      Downloads the DVF sales of the department (Etalab geo-DVF, 2022 onwards)
      and its DPE (ADEME, dpe03existant), and links each single-dwelling sale to
      the DPE of the dwelling sold: same address (BAN identifier, else street
      name and number), same kind, surface within 12 %, DPE established before
      the sale.

  fit --in DIR --out api/data/green_value.json
      Hedonic regression on the matched sales, per kind of dwelling:
      log(price/m2) = DPE class + construction period + log(surface) + quarter
      + location (squares of about 1 km, absorbed as fixed effects).
      Nationally, then per department, department estimates being shrunk
      towards the national one when their sample is small.

Only the standard library is needed for extract; fit needs numpy.
"""
import argparse
import csv
import gzip
import io
import json
import math
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

DVF_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{dep}.csv.gz"
ADEME_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
ADEME_FIELDS = ["numero_dpe", "date_etablissement_dpe", "etiquette_dpe", "type_batiment", "surface_habitable_logement",
                "identifiant_ban", "numero_voie_ban", "nom_rue_ban", "code_insee_ban", "periode_construction"]
FIRST_YEAR = 2022  # The DPE dataset starts in July 2021
UA = {"User-Agent": "sprea-green-value/1.0 (+https://sprea.vercel.app)"}

LABELS = ["A", "B", "C", "D", "E", "F", "G"]
KINDS = {"Maison": "maison", "Appartement": "appartement"}
SURFACE_TOLERANCE = 0.12
DPE_MAX_AGE_DAYS = 3 * 365
MIN_SURFACE, MIN_PRICE_M2, MAX_PRICE_M2 = 9, 300, 30000
EXCLUDED_TYPES = {"Local industriel. commercial ou assimilé"}

OUT_FIELDS = ["dep", "insee", "kind", "date", "price_m2", "surface", "label", "period", "lat", "lon", "how"]


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def fetch(url: str, retries: int = 5) -> Optional[bytes]:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            wait = 2 ** attempt * (10 if e.code == 429 else 2)
            log(f"HTTP {e.code} on {url[:120]}, retry in {wait}s")
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            wait = 2 ** attempt * 2
            log(f"{type(e).__name__} on {url[:120]}, retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {retries} attempts: {url}")


# --- Normalisation ---

def norm_street(name: str) -> str:
    name = re.sub(r"\(.*?\)", " ", name or "")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()
    name = re.sub(r"[^A-Z0-9]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def to_float(value) -> Optional[float]:
    try:
        return float(str(value).replace(",", ".")) if value not in (None, "") else None
    except ValueError:
        return None


def to_int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# --- DVF ---

def dvf_sales(rows: Iterable[Dict[str, str]]) -> List[Dict]:
    """Single-dwelling sales (house or apartment) with price per m2."""
    mutations: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("nature_mutation") == "Vente":
            mutations[row["id_mutation"]].append(row)
    sales = []
    for rows_ in mutations.values():
        if any((r.get("type_local") or "") in EXCLUDED_TYPES for r in rows_):
            continue
        dwellings = [r for r in rows_ if r.get("type_local") in KINDS]
        # The same dwelling can appear on several parcels: dedupe on (type, surface, number)
        unique = {(r["type_local"], r.get("surface_reelle_bati"), r.get("adresse_numero")) for r in dwellings}
        if len(unique) != 1:
            continue
        d = dwellings[0]
        price = to_float(d.get("valeur_fonciere"))
        surface = to_float(d.get("surface_reelle_bati"))
        carrez = to_float(d.get("lot1_surface_carrez")) if d["type_local"] == "Appartement" else None
        if carrez and surface and abs(carrez - surface) / surface < 0.25:
            surface = carrez
        if not price or not surface or surface < MIN_SURFACE:
            continue
        price_m2 = price / surface
        if not MIN_PRICE_M2 <= price_m2 <= MAX_PRICE_M2:
            continue
        sales.append({
            "kind": d["type_local"],
            "date": d["date_mutation"],
            "price_m2": price_m2,
            "surface": surface,
            "insee": d.get("code_commune") or "",
            "old_insee": d.get("ancien_code_commune") or "",
            "voie": (d.get("adresse_code_voie") or "").upper(),
            "numero": to_int(d.get("adresse_numero")),
            "street": norm_street(d.get("adresse_nom_voie") or ""),
            "lat": to_float(d.get("latitude")),
            "lon": to_float(d.get("longitude")),
        })
    return sales


def load_dvf(dep: str, last_year: int) -> List[Dict]:
    sales = []
    for year in range(FIRST_YEAR, last_year + 1):
        raw = fetch(DVF_URL.format(year=year, dep=dep))
        if raw is None:
            log(f"DVF {year} {dep}: not published")
            continue
        text = gzip.decompress(raw).decode("utf-8")
        year_sales = dvf_sales(csv.DictReader(io.StringIO(text)))
        log(f"DVF {year} {dep}: {len(year_sales)} single-dwelling sales")
        sales += year_sales
    return sales


# --- DPE ---

def load_dpe(dep: str) -> List[Dict]:
    params = {"size": "10000", "qs": f"code_departement_ban:{dep}", "select": ",".join(ADEME_FIELDS)}
    url = f"{ADEME_URL}?{urllib.parse.urlencode(params)}"
    out = []
    while url:
        page = json.loads(fetch(url))
        for r in page.get("results", []):
            kind = (r.get("type_batiment") or "").lower()
            if kind not in ("maison", "appartement") or r.get("etiquette_dpe") not in LABELS:
                continue
            out.append({
                "kind": "Maison" if kind == "maison" else "Appartement",
                "date": (r.get("date_etablissement_dpe") or "")[:10],
                "label": r["etiquette_dpe"],
                "surface": to_float(r.get("surface_habitable_logement")),
                "ban": r.get("identifiant_ban") or "",
                "insee": r.get("code_insee_ban") or "",
                "numero": to_int(r.get("numero_voie_ban")),
                "street": norm_street(r.get("nom_rue_ban") or ""),
                "period": r.get("periode_construction") or "",
            })
        url = page.get("next")
        log(f"DPE {dep}: {len(out)} / {page.get('total')}")
    return out


def ban_key(identifier: str) -> Optional[Tuple[str, str, int]]:
    """'59456_0139_00058' -> ('59456', '0139', 58)."""
    parts = identifier.split("_")
    if len(parts) < 3:
        return None
    number = to_int(parts[2])
    return (parts[0], parts[1].upper(), number) if number is not None else None


# --- Matching ---

def days_between(a: str, b: str) -> Optional[int]:
    try:
        return (date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days
    except ValueError:
        return None


def match(sales: List[Dict], dpes: List[Dict]) -> List[Dict]:
    by_ban: Dict[Tuple, List[Dict]] = defaultdict(list)
    by_street: Dict[Tuple, List[Dict]] = defaultdict(list)
    for d in dpes:
        if not d["surface"]:
            continue
        key = ban_key(d["ban"])
        if key:
            by_ban[key].append(d)
        if d["street"] and d["numero"] is not None:
            by_street[(d["insee"], d["street"], d["numero"])].append(d)

    matched = []
    for s in sales:
        if s["numero"] is None:
            continue
        candidates, how = [], ""
        for insee in filter(None, (s["insee"], s["old_insee"])):
            candidates = by_ban.get((insee, s["voie"], s["numero"]), [])
            if candidates:
                how = "ban"
                break
        if not candidates:
            candidates = by_street.get((s["insee"], s["street"], s["numero"]), [])
            how = "street"
        fits = []
        for d in candidates:
            if d["kind"] != s["kind"]:
                continue
            age = days_between(s["date"], d["date"])
            # DPE established before the sale (or within 15 days after), at most 3 years before
            if age is None or not -15 <= age <= DPE_MAX_AGE_DAYS:
                continue
            gap = abs(d["surface"] - s["surface"]) / s["surface"]
            if gap <= SURFACE_TOLERANCE:
                fits.append((gap, age, d))
        if not fits:
            continue
        fits.sort(key=lambda f: (round(f[0], 2), f[1]))
        best = fits[0]
        # Two equally plausible dwellings with different labels: ambiguous
        if any(f[2]["label"] != best[2]["label"] and abs(f[0] - best[0]) < 0.02 for f in fits[1:]):
            continue
        d = best[2]
        matched.append({
            "insee": s["insee"], "kind": s["kind"], "date": s["date"], "price_m2": round(s["price_m2"], 1),
            "surface": round(s["surface"], 1), "label": d["label"], "period": d["period"],
            "lat": s["lat"], "lon": s["lon"], "how": how,
        })
    return matched


def extract(dep: str, out_path: str) -> None:
    last_year = date.today().year
    sales = load_dvf(dep, last_year)
    if not sales:
        log(f"{dep}: no DVF sales (Alsace-Moselle and Mayotte are not covered by DVF)")
    dpes = load_dpe(dep) if sales else []
    matched = match(sales, dpes)
    hows = Counter(m["how"] for m in matched)
    log(f"{dep}: {len(matched)} matched sales out of {len(sales)} ({dict(hows)})")
    with gzip.open(out_path, "wt", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        for m in matched:
            w.writerow({**m, "dep": dep})


# --- Regression ---

PERIODS = ["avant 1948", "1948-1974", "1975-1977", "1978-1982", "1983-1988", "1989-2000", "2001-2005",
           "2006-2012", "2013-2021", "après 2021"]


def quarter(d: str) -> str:
    return f"{d[:4]}T{(int(d[5:7]) - 1) // 3 + 1}"


def cell(row: Dict) -> str:
    lat, lon = to_float(row["lat"]), to_float(row["lon"])
    if lat is None or lon is None:
        return row["insee"]
    # About 1.1 km x 1.1 km in mainland France
    return f"{row['insee']}:{round(lat * 90)}:{round(lon * 64)}"


def hedonic(rows: List[Dict], quarters: List[str]) -> Optional[Dict]:
    """OLS with location fixed effects. Returns class effects vs D (log points),
    their robust standard errors, quarter effects vs the latest quarter."""
    import numpy as np

    groups: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[cell(r)].append(i)
    keep = [i for idx in groups.values() if len(idx) >= 2 for i in idx]
    if len(keep) < 200:
        return None
    rows = [rows[i] for i in keep]
    classes = [c for c in LABELS if c != "D"]
    periods = [p for p in PERIODS if p != "1948-1974"]
    qs = quarters[:-1]  # reference: latest quarter
    names = [f"class_{c}" for c in classes] + [f"period_{p}" for p in periods] + ["log_surface"] + [f"q_{q}" for q in qs]
    X = np.zeros((len(rows), len(names)))
    y = np.zeros(len(rows))
    gid = np.zeros(len(rows), dtype=int)
    gindex: Dict[str, int] = {}
    col = {n: j for j, n in enumerate(names)}
    for i, r in enumerate(rows):
        y[i] = math.log(float(r["price_m2"]))
        if r["label"] != "D":
            X[i, col[f"class_{r['label']}"]] = 1
        if r["period"] in periods:
            X[i, col[f"period_{r['period']}"]] = 1
        X[i, col["log_surface"]] = math.log(float(r["surface"]))
        q = quarter(r["date"])
        if f"q_{q}" in col:
            X[i, col[f"q_{q}"]] = 1
        gid[i] = gindex.setdefault(cell(r), len(gindex))
    # Within transformation (absorbs the location fixed effects)
    counts = np.bincount(gid)
    def demean(v):
        return v - (np.bincount(gid, weights=v) / counts)[gid]
    yd = demean(y)
    Xd = np.column_stack([demean(X[:, j]) for j in range(X.shape[1])])
    used = Xd.std(axis=0) > 1e-9
    Xu = Xd[:, used]
    beta, *_ = np.linalg.lstsq(Xu, yd, rcond=None)
    resid = yd - Xu @ beta
    n, k, g = len(rows), Xu.shape[1], len(gindex)
    xtx_inv = np.linalg.pinv(Xu.T @ Xu)
    xe = Xu * resid[:, None]
    cov = xtx_inv @ (xe.T @ xe) @ xtx_inv * n / max(1, n - k - g)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    full_beta = dict.fromkeys(names, None)
    full_se = dict.fromkeys(names, None)
    for name, b, s in zip([nm for nm, u in zip(names, used) if u], beta, se):
        full_beta[name], full_se[name] = float(b), float(s)
    label_counts = Counter(r["label"] for r in rows)
    return {
        "n": n,
        "class": {c: (0.0 if c == "D" else full_beta[f"class_{c}"]) for c in LABELS},
        "class_se": {c: (0.0 if c == "D" else full_se[f"class_{c}"]) for c in LABELS},
        "class_n": {c: label_counts.get(c, 0) for c in LABELS},
        "quarter": {q: (0.0 if q == quarters[-1] else full_beta.get(f"q_{q}")) for q in quarters},
        "r2_within": float(1 - (resid @ resid) / (yd @ yd)) if yd @ yd > 0 else None,
    }


def shrink(dep_fit: Dict, nat: Dict, tau2: Dict[str, float]) -> Dict[str, float]:
    out = {}
    for c in LABELS:
        b, se = dep_fit["class"].get(c), dep_fit["class_se"].get(c)
        if c == "D":
            out[c] = 0.0
        elif b is None or se is None or dep_fit["class_n"][c] < 10:
            out[c] = nat["class"][c]
        else:
            w = tau2[c] / (tau2[c] + se ** 2)
            out[c] = w * b + (1 - w) * nat["class"][c]
    return out


def summary_markdown(new: Dict, old: Optional[Dict]) -> str:
    """PR description: sample sizes and national class gaps, with the change since the previous file."""
    lines = [f"Mise à jour mensuelle des écarts de prix entre classes DPE ({new.get('period')}).", ""]
    for kind, label in (("Maison", "Maisons"), ("Appartement", "Appartements")):
        nat = new["kinds"].get(kind, {}).get("national")
        if not nat:
            continue
        prev = ((old or {}).get("kinds", {}).get(kind) or {}).get("national")
        lines += [f"### {label} : {nat['n']:,} ventes rapprochées de leur DPE".replace(",", " "), "",
                  "| Classe | Écart vs D | Mois précédent |", "|---|---|---|"]
        for c in LABELS:
            pct = (math.exp(nat["class"][c]) - 1) * 100
            before = f"{(math.exp(prev['class'][c]) - 1) * 100:+.1f} %" if prev else "–"
            lines.append(f"| {c} | {pct:+.1f} % | {before} |")
        lines.append("")
    deps = {k: len(v.get("departments", {})) for k, v in new["kinds"].items()}
    lines.append(f"Départements estimés : {deps}. À relire avant fusion : des écarts qui bougent de plus de quelques points "
                 "d'un mois sur l'autre méritent une vérification des données sources.")
    return "\n".join(lines)


def fit(in_dir: str, out_path: str, summary_path: Optional[str] = None) -> None:
    import glob
    import os

    old = None
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            old = json.load(f)

    rows: List[Dict] = []
    for path in sorted(glob.glob(f"{in_dir}/**/matched_*.csv.gz", recursive=True)):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            rows += list(csv.DictReader(f))
    log(f"{len(rows)} matched sales")
    quarters = sorted({quarter(r["date"]) for r in rows})
    result = {"generated": date.today().isoformat(), "period": f"{quarters[0]}-{quarters[-1]}" if quarters else None,
              "latest_quarter": quarters[-1] if quarters else None, "kinds": {}}
    for kind in KINDS:
        kind_rows = [r for r in rows if r["kind"] == kind]
        nat = hedonic(kind_rows, quarters)
        if not nat:
            continue
        log(f"{kind} national: n={nat['n']} " + " ".join(f"{c}={nat['class'][c]:+.3f}" for c in LABELS))
        by_dep: Dict[str, List[Dict]] = defaultdict(list)
        for r in kind_rows:
            by_dep[r["dep"]].append(r)
        dep_fits = {}
        for dep, dep_rows in sorted(by_dep.items()):
            f = hedonic(dep_rows, quarters)
            if f:
                dep_fits[dep] = f
        # Between-department variance of each class effect (method of moments)
        tau2 = {}
        for c in LABELS:
            vals = [(f["class"][c], f["class_se"][c]) for f in dep_fits.values()
                    if f["class"][c] is not None and f["class_n"][c] >= 50 and c != "D"]
            if len(vals) >= 5:
                mean = sum(v for v, _ in vals) / len(vals)
                var = sum((v - mean) ** 2 for v, _ in vals) / (len(vals) - 1)
                tau2[c] = max(0.0004, var - sum(s ** 2 for _, s in vals) / len(vals))
            else:
                tau2[c] = 0.0004
        departments = {}
        for dep, dep_rows in by_dep.items():
            mix = Counter(r["label"] for r in dep_rows)
            total = sum(mix.values())
            entry = {"n": len(dep_rows), "mix": {c: round(mix.get(c, 0) / total, 4) for c in LABELS}}
            f = dep_fits.get(dep)
            if f:
                entry["class"] = {c: round(v, 4) for c, v in shrink(f, nat, tau2).items()}
                entry["class_se"] = {c: round(f["class_se"][c] or 0, 4) for c in LABELS}
                if f["n"] >= 2000:
                    entry["quarter"] = {q: round(v, 4) for q, v in f["quarter"].items() if v is not None}
            departments[dep] = entry
        mix = Counter(r["label"] for r in kind_rows)
        result["kinds"][kind] = {
            "national": {
                "n": nat["n"],
                "class": {c: round(v, 4) for c, v in nat["class"].items()},
                "class_se": {c: round(v or 0, 4) for c, v in nat["class_se"].items()},
                "quarter": {q: round(v, 4) for q, v in nat["quarter"].items() if v is not None},
                "mix": {c: round(mix.get(c, 0) / len(kind_rows), 4) for c in LABELS},
                "r2_within": round(nat["r2_within"], 3) if nat["r2_within"] is not None else None,
            },
            "departments": departments,
        }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, sort_keys=True)
    log(f"Written {out_path}")
    if summary_path:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_markdown(result, old))


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--dep", required=True)
    e.add_argument("--out", required=True)
    f = sub.add_parser("fit")
    f.add_argument("--in", dest="in_dir", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--summary")
    args = parser.parse_args(argv)
    if args.cmd == "extract":
        extract(args.dep, args.out)
    else:
        fit(args.in_dir, args.out, args.summary)


if __name__ == "__main__":
    main()
