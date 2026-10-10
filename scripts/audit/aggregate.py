"""Merges the shards of a large audit: totals, anomalies grouped by kind
(numbers removed), and the before/after comparison over every shard.

  python scripts/audit/aggregate.py shards/
"""
import glob
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def main(folder: str):
    results = []
    for path in sorted(glob.glob(os.path.join(folder, "**", "audit.json"), recursive=True)):
        results += json.load(open(path))
    failed = [r for r in results if r["failures"]]
    by_kind = Counter(r["kind"] for r in results)
    ko_kind = Counter(r["kind"] for r in failed)
    groups = Counter()
    examples = {}
    for r in failed:
        for f in r["failures"]:
            key = re.sub(r"\d[\d  .,]*", "#", f.split(" : ")[0] if f.startswith("erreur") else f)
            key = re.sub(r"«[^»]*»", "«…»", key)[:140]
            groups[key] += 1
            examples.setdefault(key, f"{r['name']} ({'; '.join(r['notes'][:1])}) : {f}")
    lines = [f"# Audit complet : {len(results) - len(failed)} / {len(results)} cas sans anomalie", ""]
    lines += [f"- {k} : {by_kind[k] - ko_kind[k]} OK, {ko_kind[k]} KO" for k in by_kind]
    notes = Counter()
    for r in results:
        for n in r["notes"]:
            if n.startswith(("Maison", "Appartement", "Immeuble", "maison", "appartement", "immeuble")):
                parts = n.split()
                notes[(parts[0].capitalize(), parts[3] if len(parts) > 3 else "?")] += 1
    if notes:
        kinds = sorted({k for k, _ in notes})
        lines += ["", "| Type | " + " | ".join("ABCDEFG") + " |", "|---|" + "---|" * 7]
        lines += [f"| {k} | " + " | ".join(str(notes.get((k, l), 0)) for l in "ABCDEFG") + " |" for k in kinds]
    if groups:
        lines += ["", "## Anomalies par type", "", "| Nombre | Anomalie | Exemple |", "|---|---|---|"]
        lines += [f"| {n} | {k} | {examples[k]} |" for k, n in groups.most_common(60)]
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text + "\n")
    # Before/after over every shard
    base, new = {}, {}
    for path in glob.glob(os.path.join(folder, "**", "sel_base.json"), recursive=True):
        base.update(json.load(open(path)))
    for path in glob.glob(os.path.join(folder, "**", "sel_new.json"), recursive=True):
        new.update(json.load(open(path)))
    if base and new:
        json.dump(base, open("all_base.json", "w"))
        json.dump(new, open("all_new.json", "w"))
        from scripts.audit.compare import main as compare
        compare("all_base.json", "all_new.json")


if __name__ == "__main__":
    main(sys.argv[1])
