"""Merges the shards of the expert review: findings by category and severity,
with examples, and every blocking finding.

  python scripts/audit/review_aggregate.py shards/
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

SEVERITY = {"bloquant": 0, "important": 1, "mineur": 2}


def main(folder: str):
    rows = []
    for path in sorted(glob.glob(os.path.join(folder, "**", "reviews.json"), recursive=True)):
        rows += json.load(open(path))
    done = [r for r in rows if "error" not in r]
    errors = [r for r in rows if "error" in r]
    clean = [r for r in done if not r.get("findings")]
    findings = [(r, f) for r in done for f in r.get("findings") or []]
    by_cat = defaultdict(list)
    for r, f in findings:
        by_cat[f["category"]].append((r, f))
    sev = Counter(f["severity"] for _, f in findings)
    worst = Counter(min((SEVERITY[f["severity"]] for f in r.get("findings") or []), default=3) for r in done)
    lines = [f"# Relecture experte : {len(done)} rapports, {len(clean)} sans défaut",
             "",
             f"- Rapports avec au moins un défaut bloquant : {worst[0]} ; important (sans bloquant) : {worst[1]} ; seulement mineurs : {worst[2]}",
             f"- Défauts : {len(findings)} ({sev['bloquant']} bloquants, {sev['important']} importants, {sev['mineur']} mineurs)",
             f"- Analyse rédigée par Claude : {sum(1 for r in done if r.get('analysis_source') == 'claude')} / {len(done)}",
             f"- Erreurs de génération : {len(errors)}" + (f" ({'; '.join(r['error'][:80] for r in errors[:3])})" if errors else ""),
             f"- Contrôles automatiques en défaut : {sum(1 for r in done if r.get('checks'))} rapports"
             + "".join(f"\n  - {r['number']} : {' ; '.join(r['checks'])[:300]}" for r in done if r.get("checks")),
             "", "## Par catégorie", "", "| Catégorie | Bloquants | Importants | Mineurs |", "|---|---|---|---|"]
    for cat, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        c = Counter(f["severity"] for _, f in items)
        lines.append(f"| {cat} | {c['bloquant']} | {c['important']} | {c['mineur']} |")
    lines += ["", "## Défauts bloquants et importants", ""]
    for cat, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        serious = sorted((x for x in items if x[1]["severity"] != "mineur"), key=lambda x: SEVERITY[x[1]["severity"]])
        if not serious:
            continue
        lines.append(f"### {cat} ({len(serious)})")
        for r, f in serious[:40]:
            lines.append(f"- [{f['severity']}] {r['number']} ({r.get('kind')} {r.get('surface')} m² {r.get('label')}→{r.get('new_label')}, "
                         f"{'+'.join(r.get('works') or []) or 'aucun travaux'}) : {f['finding']} — « {f['excerpt'][:200]} »")
        lines.append("")
    lines += ["## Mineurs (échantillon)", ""]
    minor = [(r, f) for r, f in findings if f["severity"] == "mineur"]
    for r, f in minor[:40]:
        lines.append(f"- {r['number']} [{f['category']}] {f['finding']} — « {f['excerpt'][:140]} »")
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
