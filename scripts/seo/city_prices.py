"""Price per m2 of each commune, from the DVF open data, for the public
« Prix m² à <commune> » pages (/prix-m2/<slug>-<insee>).

  python scripts/seo/city_prices.py extract --dep 59 --out prix_59.json
  python scripts/seo/city_prices.py combine --in parts --index src/data/prix_index.json --out public/prix

extract: the sales of the department over the three most recent published
years, filtered like the estimator (api/dvf.parse_sales: single-dwelling
sales, outliers out), then per commune and per kind (apartment, house) over
the two most recent years: median price per m2 with the interquartile range,
number of sales, median surface and price, the median of each of the three
years, and by number of rooms. Paris, Lyon and Marseille also get a city
figure gathering their arrondissements.

combine: names, population and centres of the communes (geo.api.gouv.fr),
the six closest communes kept, the DPE class effects of the department
(api/data/green_value.json); writes one file per department for the pages
and a small index for the prerender and the list page.
"""
import argparse
import gzip
import json
import math
import os
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.dvf import distance_m, parse_sales  # noqa: E402
from api.green_value import class_premium  # noqa: E402

DVF_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{dep}.csv.gz"
GEO_COMMUNES = "https://geo.api.gouv.fr/communes?fields=nom,code,codeDepartement,population,centre&format=json"
GEO_ARRONDISSEMENTS = GEO_COMMUNES + "&type=arrondissement-municipal"
GEO_DEPARTEMENTS = "https://geo.api.gouv.fr/departements?fields=nom,code"
KINDS = {"appartement": "Appartement", "maison": "Maison"}
# A commune gets a page from this many sales over the two years (both kinds)
MIN_SALES = 30
# A figure (a kind, a year, a number of rooms) is shown from this many sales
MIN_FIGURE = 8
CITIES = {"75056": ("751", "Paris"), "69123": ("6938", "Lyon"), "13055": ("132", "Marseille")}


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def fetch(url: str, retries: int = 5) -> Optional[bytes]:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SPREA"}), timeout=120) as res:
                return res.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return None
            log(f"{url}: HTTP {e.code}, retry")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            log(f"{url}: {e}, retry")
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{url}: failed")


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode().lower()
    out = "".join(c if c.isalnum() else "-" for c in s)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def figure(sales: List[Dict]) -> Optional[Dict]:
    if len(sales) < MIN_FIGURE:
        return None
    m2 = sorted(s["price_m2"] for s in sales)
    q = statistics.quantiles(m2, n=4)
    return {"m2": round(statistics.median(m2)), "q25": round(q[0]), "q75": round(q[2]), "n": len(sales),
            "surface": round(statistics.median(s["surface"] for s in sales)),
            "price": round(statistics.median(s["price"] for s in sales), -3)}


def stats(sales: List[Dict], years: List[int]) -> Optional[Dict]:
    """years: most recent first. The headline figure uses the two most recent."""
    recent = [s for s in sales if s["year"] in years[:2]]
    head = figure(recent)
    if not head:
        return None
    by_year = {}
    for y in years:
        f = figure([s for s in sales if s["year"] == y])
        if f:
            by_year[str(y)] = {"m2": f["m2"], "n": f["n"]}
    rooms = {}
    for r in range(1, 6):
        group = [s for s in recent if s.get("rooms") and (int(s["rooms"]) == r if r < 5 else int(s["rooms"]) >= 5)]
        f = figure(group)
        if f:
            rooms[str(r)] = {"m2": f["m2"], "price": f["price"], "surface": f["surface"], "n": f["n"]}
    return {**head, "years": by_year, "rooms": rooms}


def extract(dep: str, out_path: str) -> None:
    today = date.today()
    years, raw = [], {}
    for year in range(today.year, today.year - 8, -1):
        data = fetch(DVF_URL.format(year=year, dep=dep))
        if data is None:
            continue
        raw[year] = gzip.decompress(data).decode("utf-8")
        years.append(year)
        if len(years) == 3:
            break
    log(f"{dep}: years {years}")
    by_commune: Dict[str, Dict[str, List[Dict]]] = {}
    for year in years:
        for kind, label in KINDS.items():
            for s in parse_sales(raw[year], label, year):
                code = s.get("insee")
                if not code:
                    continue
                for c in [code] + [city for city, (prefix, _) in CITIES.items() if code.startswith(prefix) and code != city]:
                    by_commune.setdefault(c, {}).setdefault(kind, []).append(s)
        raw.pop(year)
    out = {}
    for code, kinds in by_commune.items():
        recent = sum(1 for k in kinds.values() for s in k if s["year"] in years[:2])
        if recent < MIN_SALES:
            continue
        entry = {k: stats(v, years) for k, v in kinds.items()}
        entry = {k: v for k, v in entry.items() if v}
        if entry:
            out[code] = {"kinds": entry, "sales": recent}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"dep": dep, "years": years, "communes": out}, f, ensure_ascii=False)
    log(f"{dep}: {len(out)} communes")


def dpe_effects(dep: str) -> Dict[str, Dict[str, float]]:
    """Price gap of each DPE class against D, in %, measured in the department (api/green_value.py)."""
    out = {}
    for kind, label in KINDS.items():
        premium = class_premium(label, dep)
        if premium:
            out[kind] = premium
    return out


def combine(in_dir: str, index_path: str, out_dir: str) -> None:
    parts = [json.load(open(os.path.join(in_dir, f), encoding="utf-8")) for f in sorted(os.listdir(in_dir)) if f.endswith(".json")]
    geo = {c["code"]: c for c in json.loads(fetch(GEO_COMMUNES))}
    geo.update({c["code"]: c for c in json.loads(fetch(GEO_ARRONDISSEMENTS))})
    deps = {d["code"]: d["nom"] for d in json.loads(fetch(GEO_DEPARTEMENTS))}
    years = max((p["years"] for p in parts), key=lambda y: y[0] if y else 0)
    kept: Dict[str, Dict] = {}
    for p in parts:
        for code, e in p["communes"].items():
            g = geo.get(code)
            if not g:
                continue
            name = g["nom"]
            # « Paris 15e Arrondissement » -> « Paris 15e »
            name = name.replace(" Arrondissement", "")
            coords = (g.get("centre") or {}).get("coordinates") or [None, None]
            parent = next((city for city, (prefix, _) in CITIES.items() if code.startswith(prefix) and code != city), None)
            kept[code] = {"code": code, "name": name, "slug": f"{slugify(name)}-{code.lower()}", "dep": p["dep"],
                          "depName": deps.get(p["dep"], p["dep"]), "pop": g.get("population"), "lat": coords[1], "lon": coords[0],
                          "parent": parent, **e}
    for city in CITIES:
        if city in kept:
            kept[city]["children"] = sorted((c for c, v in kept.items() if v.get("parent") == city), key=lambda c: c)
    # Six closest communes of the same department with a page: an arrondissement
    # links the other arrondissements of its city, a commune the other communes
    for code, c in kept.items():
        pool = [o for o in kept.values() if o["code"] != code and o["dep"] == c["dep"] and o["lat"] is not None
                and o.get("parent") == c.get("parent")]
        if c["lat"] is not None:
            pool.sort(key=lambda o: distance_m(c["lat"], c["lon"], o["lat"], o["lon"]))
        c["near"] = [o["code"] for o in pool[:6]]
    os.makedirs(out_dir, exist_ok=True)
    by_dep: Dict[str, Dict] = {}
    for code, c in kept.items():
        by_dep.setdefault(c["dep"], {})[code] = c
    for dep, communes in by_dep.items():
        # Names of the neighbours, so the page links them without loading other files
        names = {o: {"name": kept[o]["name"], "slug": kept[o]["slug"],
                     "m2": (kept[o]["kinds"].get("appartement") or kept[o]["kinds"].get("maison") or {}).get("m2")}
                 for c in communes.values() for o in c["near"] + c.get("children", []) + ([c["parent"]] if c.get("parent") else [])}
        with open(os.path.join(out_dir, f"{dep}.json"), "w", encoding="utf-8") as f:
            json.dump({"dep": dep, "depName": deps.get(dep, dep), "years": years, "updated": date.today().isoformat(),
                       "dpe": dpe_effects(dep), "communes": communes, "names": names}, f, ensure_ascii=False, separators=(",", ":"))
    index = sorted(({"c": c["code"], "n": c["name"], "s": c["slug"], "d": c["dep"], "p": c.get("pop") or 0,
                     "a": (c["kinds"].get("appartement") or {}).get("m2"), "m": (c["kinds"].get("maison") or {}).get("m2"),
                     "k": c["sales"]} for c in kept.values()), key=lambda r: (-r["k"], r["n"]))
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"updated": date.today().isoformat(), "years": years, "deps": deps, "communes": index}, f,
                  ensure_ascii=False, separators=(",", ":"))
    log(f"{len(kept)} communes in {len(by_dep)} departments")


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--dep", required=True)
    e.add_argument("--out", required=True)
    c = sub.add_parser("combine")
    c.add_argument("--in", dest="in_dir", required=True)
    c.add_argument("--index", required=True)
    c.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        extract(args.dep, args.out)
    else:
        combine(args.in_dir, args.index, args.out)


if __name__ == "__main__":
    main()
