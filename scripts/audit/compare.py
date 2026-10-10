"""Before/after comparison of the default selection (selection.py run on the
base branch and on the change), printed and added to the job summary.

  python scripts/audit/compare.py base.json new.json
"""
import json
import os
import sys
from statistics import median

LABELS = "ABCDEFG"


def main(base_path: str, new_path: str):
    base, new = json.load(open(base_path)), json.load(open(new_path))
    common = [n for n in new if n in base and "error" not in new[n] and "error" not in base[n]]
    changed = [n for n in common if base[n]["works"] != new[n]["works"]]
    worse = [n for n in changed if LABELS.index(new[n]["new_label"]) > LABELS.index(base[n]["new_label"])]
    better = [n for n in changed if LABELS.index(new[n]["new_label"]) < LABELS.index(base[n]["new_label"])]
    lost_ampleur = [n for n in changed if base[n]["pathway"] == "accompagne" and new[n]["pathway"] != "accompagne"]
    gained_ampleur = [n for n in changed if base[n]["pathway"] != "accompagne" and new[n]["pathway"] == "accompagne"]
    deltas = [new[n]["cost"] - base[n]["cost"] for n in changed]
    rest = [new[n]["rest"] - base[n]["rest"] for n in changed]
    errors = [n for n in new if "error" in new[n]]
    lines = [f"## Sélection par défaut : avant / après ({len(common)} logements)", "",
             f"- Programme inchangé : {len(common) - len(changed)}",
             f"- Programme modifié : {len(changed)}"]
    if changed:
        lines += [f"  - classe finale moins bonne : {len(worse)} ; meilleure : {len(better)} ; identique : {len(changed) - len(worse) - len(better)}",
                  f"  - rénovation d'ampleur perdue : {len(lost_ampleur)} ; gagnée : {len(gained_ampleur)}",
                  f"  - coût : médiane {median(deltas):+.0f} €, de {min(deltas):+.0f} à {max(deltas):+.0f} €",
                  f"  - reste à charge : médiane {median(rest):+.0f} €, de {min(rest):+.0f} à {max(rest):+.0f} €"]
    if errors:
        lines.append(f"- Erreurs : {len(errors)} ({'; '.join(new[n]['error'] for n in errors[:3])})")
    lines += ["", "| DPE | Bien | Avant | Après |", "|---|---|---|---|"]
    for n in sorted(changed, key=lambda n: (n not in worse and n not in lost_ampleur, n))[:80]:
        b, a = base[n], new[n]
        flag = " ⚠" if n in worse or n in lost_ampleur else ""
        lines.append(f"| {n}{flag} | {a['kind']} {a['surface']:g} m² {a['label']} | {'+'.join(b['works'])} → {b['new_label']}, "
                     f"{b['cost']} €, reste {b['rest']} €, {b['pathway']} | {'+'.join(a['works'])} → {a['new_label']}, {a['cost']} €, "
                     f"reste {a['rest']} €, {a['pathway']} |")
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
