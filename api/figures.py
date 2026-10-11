"""Costs, aids and rest to pay as every document shows them (report, its
written analysis, avis de valeur), rounded once so that each sum holds:
total = sum of the lines, cost - aids = rest to pay."""
from typing import Any, Dict, List, Optional


def r(value: Optional[float], step: int = 100) -> int:
    return int(round((value or 0) / step) * step)


def display_figures(sim: Dict[str, Any], works: List[Dict[str, Any]],
                    extras: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
    """`works`: the lines shown (cost_low, cost_high, and the aid per work
    when the report details it); `extras`: other costs (parking)."""
    extra = sum(r(x["cost"], 10) for x in extras or [])
    low = sum(r(w["cost_low"]) for w in works) + extra
    high = sum(r(w["cost_high"]) for w in works) + extra
    if sim["aid_pathway"] == "accompagne":
        mpr, cee = r(sim["subsidies"]), 0
        aids = mpr
        aids_low, aids_high = r(sim.get("aids_low", sim["subsidies"])), r(sim.get("aids_high", sim["subsidies"]))
    else:
        per_work = sum(r(w["aid"], 10) for w in works if w.get("aid"))
        mpr = r(sim["subsidies"], 10)
        # The CEE line closes the sum of the amounts per work
        cee = max(0, per_work - mpr) if per_work else r(sim["cee_est"], 10)
        aids = aids_low = aids_high = mpr + cee
    cost = r(sim["cost"])
    rest = max(0, cost - aids)
    # The loan never exceeds the rest to pay it finances, once both are rounded
    eco_ptz = min(r(sim.get("eco_ptz_amount")), rest // 100 * 100) if sim.get("eco_ptz_amount") else 0
    return {"eco_ptz": eco_ptz, "cost": cost, "cost_low": low, "cost_high": high, "mpr": mpr, "cee": cee, "aids": aids,
            "aids_low": aids_low, "aids_high": aids_high, "rest": max(0, cost - aids),
            "rest_low": max(0, low - aids_low), "rest_high": max(0, high - aids_high)}


def green_range_shown(sim: Dict[str, Any]) -> bool:
    """The 95 % range of the green value, unless so wide (few comparable
    sales) that it says nothing: "0 € à 134 000 €" for a value of 20 000 €."""
    value, low, high = sim.get("latent_gain") or 0, sim.get("latent_gain_low") or 0, sim.get("latent_gain_high") or 0
    return not (low < value * 0.3 or high > value * 3)
