"""Green value ("valeur verte") of the works: how much the dwelling's market
value moves when it changes DPE class.

The class effects come from api/data/green_value.json, measured on real sales
(DVF sales linked to the DPE of the dwelling sold, scripts/green_value/build.py):
log price per m2 by class, relative to D, per department and kind of dwelling.
The local price per m2 (api/dvf.py) is a median over sales of all classes, so
it is first brought back to the dwelling's own class using the department's
class mix. Without the data file, a flat rate per class gained is used.
"""
import json
import math
import os
from functools import lru_cache
from typing import Dict, Optional

LABELS = ["A", "B", "C", "D", "E", "F", "G"]
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "green_value.json")

# Fallback: average gap per class from the notaries' studies (Notaires de France)
FLAT_RATE_PER_CLASS = 0.045
Z_95 = 1.96


@lru_cache(maxsize=1)
def load(path: str = DATA_PATH) -> Optional[Dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def department(insee: Optional[str], postcode: Optional[str]) -> Optional[str]:
    code = (insee or "").strip().upper()
    if len(code) == 5:
        return code[:3] if code.startswith("97") else code[:2]
    pc = (postcode or "").strip()
    if len(pc) != 5 or not pc.isdigit():
        return None
    if pc.startswith("97"):
        return pc[:3]
    if pc.startswith("20"):
        return "2A" if pc < "20200" else "2B"
    return pc[:2]


def kind_of(building_type: Optional[str]) -> str:
    return "Maison" if "maison" in (building_type or "").lower() else "Appartement"


def model(kind: str, dep: Optional[str], data: Optional[Dict] = None) -> Optional[Dict]:
    """Class effects for this kind of dwelling in this department (national as fallback)."""
    data = data if data is not None else load()
    if not data or kind not in data.get("kinds", {}):
        return None
    k = data["kinds"][kind]
    nat = k["national"]
    d = k.get("departments", {}).get(dep or "", {})
    scope = "department" if "class" in d else "national"
    return {
        "class": d.get("class") or nat["class"],
        "class_se": d.get("class_se") if "class" in d else nat["class_se"],
        "mix": d.get("mix") or nat["mix"],
        "quarter": d.get("quarter") or nat.get("quarter") or {},
        "scope": scope,
        "n": d.get("n") if scope == "department" else nat["n"],
        "period": data.get("period"),
    }


def quarter_index(kind: str, dep: Optional[str], data: Optional[Dict] = None) -> Dict[str, float]:
    """Log price change of each quarter vs the latest one (to bring old sales to today)."""
    m = model(kind, dep, data)
    return m["quarter"] if m else {}


def class_premium(kind: str, dep: Optional[str], data: Optional[Dict] = None) -> Optional[Dict[str, float]]:
    """Price of each class relative to D, in % (e.g. {'G': -14.2, ...}), for display."""
    m = model(kind, dep, data)
    if not m:
        return None
    return {c: round((math.exp(m["class"][c]) - 1) * 100, 1) for c in LABELS}


def estimate(current: str, target: str, surface: float, price_m2: float, kind: str, dep: Optional[str],
             data: Optional[Dict] = None) -> Dict:
    """Value gained by moving from class `current` to `target`, with a 95 % range."""
    if current not in LABELS or target not in LABELS or LABELS.index(target) >= LABELS.index(current):
        return {"value": 0.0, "low": 0.0, "high": 0.0, "method": "none", "basis": None}
    m = model(kind, dep, data)
    base = surface * price_m2
    if not m:
        steps = LABELS.index(current) - LABELS.index(target)
        value = steps * base * FLAT_RATE_PER_CLASS
        return {"value": value, "low": value * 0.5, "high": value * 1.5, "method": "flat",
                "basis": f"moyenne nationale de {FLAT_RATE_PER_CLASS * 100:.1f} % par classe gagnée".replace(".", ",")}

    b = m["class"]
    # The local median mixes all classes: average class effect of the local sales
    mix_level = sum(m["mix"].get(c, 0) * math.exp(b[c]) for c in LABELS) or 1.0
    value_now = base * math.exp(b[current]) / mix_level
    delta = b[target] - b[current]
    se = math.sqrt((m["class_se"].get(target) or 0) ** 2 + (m["class_se"].get(current) or 0) ** 2)

    def gain(d: float) -> float:
        return max(0.0, value_now * (math.exp(d) - 1))

    scope = "du département" if m["scope"] == "department" else "nationales"
    period = m["period"] or ""
    # "2022T1-2025T4" -> "2022 à 2025"
    years = period.replace("T1", "").replace("T2", "").replace("T3", "").replace("T4", "").split("-")
    period = f"{years[0]} à {years[-1]}" if len(years) == 2 and years[0] != years[-1] else period
    return {
        "value": gain(delta),
        "low": gain(delta - Z_95 * se),
        "high": gain(delta + Z_95 * se),
        "method": m["scope"],
        "value_now": value_now,
        "premium_pct": round((math.exp(delta) - 1) * 100, 1),
        "basis": (f"écart de prix mesuré entre les classes {current} et {target} sur les ventes {scope} "
                  f"({format(m['n'], ',').replace(',', ' ')} ventes rapprochées de leur DPE, {period})"),
    }
