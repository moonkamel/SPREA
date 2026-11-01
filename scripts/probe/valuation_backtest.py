"""Backtest of the house valuation on real sales of a department: each house
sold in 2024-2025 whose DPE is known (DVF x ADEME, as scripts/green_value)
is valued from the other sales of its commune, then compared to its price.
Variants: with or without the land band, and with the DPE class factor at
0 %, 50 %, 75 % or 100 % of its measured strength."""
import csv
import gzip
import io
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/green_value")
import build  # noqa: E402
from api import dvf  # noqa: E402
from api.green_value import model, quarter_index  # noqa: E402
from api.valuation import class_factor  # noqa: E402

DEP = sys.argv[1] if len(sys.argv) > 1 else "62"
LIMIT = 2500


def key(date, price_m2, lat, lon):
    return (date[:10], round(price_m2), round(lat or 0, 4), round(lon or 0, 4))


def main():
    build_sales, pool = [], defaultdict(list)
    for year in range(2022, 2026):
        raw = build.fetch(build.DVF_URL.format(year=year, dep=DEP))
        if raw is None:
            continue
        text = gzip.decompress(raw).decode("utf-8")
        build_sales += [s for s in build.dvf_sales(csv.DictReader(io.StringIO(text))) if s["kind"] == "Maison"]
        for s in dvf.parse_sales(text, "Maison", year):
            pool[s["insee"]].append(s)
    index = quarter_index("Maison", DEP)
    for sales in pool.values():
        dvf.adjust_to_today(sales, index)
    by_key = {key(s["date"], s["price_m2"], s["lat"], s["lon"]): s for sales in pool.values() for s in sales}
    matched = [m for m in build.match(build_sales, build.load_dpe(DEP)) if m["date"] >= "2024-01-01"]
    print(f"Dep {DEP}: {len(build_sales)} house sales, {len(matched)} matched with a DPE in 2024-2025", flush=True)
    m = model("Maison", DEP)
    alphas = (0, 0.5, 0.75, 1)
    errors = defaultdict(list)
    done = 0
    for row in matched:
        sale = by_key.get(key(row["date"], row["price_m2"], row["lat"], row["lon"]))
        if not sale or row["label"] not in "ABCDEFG":
            continue
        others = [s for s in pool[sale["insee"]] if s is not sale]
        actual = sale["adjusted_m2"]
        group = "A-C" if row["label"] in "ABC" else "D-E" if row["label"] in "DE" else "F-G"
        for variant, land in (("sans terrain", None), ("avec terrain", sale.get("land"))):
            res = dvf.summarize(others, "Maison", sale["lat"], sale["lon"], sale["surface"], adjusted=True, land=land)
            if not res:
                continue
            for a in alphas:
                f = class_factor(m, row["label"]) ** a
                err = res["price_per_m2"] * f / actual - 1
                for g in (group, "toutes"):
                    errors[(variant, a, g)].append(err)
            if variant == "avec terrain":
                errors[("terrain utilisé", 1, "toutes")].append(1 if res.get("land_matched") else 0)
        done += 1
        if done >= LIMIT:
            break
    print(f"{done} maisons évaluées\n")
    print("variante | décote DPE | classes | n | biais médian | erreur absolue médiane | part à ±10 %")
    for (variant, a, g), errs in sorted(errors.items()):
        if variant == "terrain utilisé":
            print(f"Terrain comparable trouvé pour {100 * sum(errs) / len(errs):.0f} % des maisons")
            continue
        within = sum(1 for e in errs if abs(e) <= 0.10) / len(errs)
        print(f"{variant} | {int(a * 100)} % | {g} | {len(errs)} | {100 * statistics.median(errs):+.1f} % | "
              f"{100 * statistics.median(abs(e) for e in errs):.1f} % | {100 * within:.0f} %")


main()
