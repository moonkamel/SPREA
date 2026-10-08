"""Avis de valeur "avant / après rénovation" (Pro).

Value today: price per m2 of comparable DVF sales around the dwelling
(api/dvf.py), brought back to the dwelling's own DPE class with the class
effects measured on real sales in its department (api/green_value.py), then
the agent's own adjustment (condition, floor, outdoor space...).
Value after works: the same, at the class reached by the works simulated with
the engine (api/simulation.py), which also gives costs and aids.
"""
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

try:
    from api.accounts import ReportMeta, is_pro, safe_filename, store_dep
    from api.auth import User, current_user
    from api.dvf import market_price
    from api.green_value import LABELS, department, kind_of, model
    from api.pdf_service import pdf_service
    from api.report_content import display_address
    from api.simulation import SimulationInput, simulate
    from api.store import SupabaseStore
except ImportError:
    from accounts import ReportMeta, is_pro, safe_filename, store_dep
    from auth import User, current_user
    from dvf import market_price
    from green_value import LABELS, department, kind_of, model
    from pdf_service import pdf_service
    from report_content import display_address
    from simulation import SimulationInput, simulate
    from store import SupabaseStore

router = APIRouter(prefix="/api")


def round_value(v: float) -> int:
    """Values are rounded to 1 000 € (to 500 € under 100 000 €)."""
    step = 500 if v < 100000 else 1000
    return int(round(v / step) * step)


def class_factor(m: Optional[Dict[str, Any]], label: str) -> float:
    """Price of a dwelling of this class relative to the local median (all classes mixed)."""
    if not m or label not in LABELS:
        return 1.0
    mix_level = sum(m["mix"].get(c, 0) * math.exp(m["class"][c]) for c in LABELS) or 1.0
    return math.exp(m["class"][label]) / mix_level


def compute(sim: Dict[str, Any], market: Dict[str, Any], surface: float, kind: str, dep: Optional[str],
            adjustment_pct: float) -> Dict[str, Any]:
    m = model(kind, dep)
    adj = 1 + adjustment_pct / 100
    current, target = sim["current_label"], sim["new_label"]
    f_now, f_after = class_factor(m, current), class_factor(m, target)

    def values(price_m2: float, factor: float) -> float:
        return surface * price_m2 * factor * adj

    now = {k: values(market[p], f_now) for k, p in (("value", "price_per_m2"), ("low", "q25"), ("high", "q75"))}
    after = {k: values(market[p], f_after) for k, p in (("value", "price_per_m2"), ("low", "q25"), ("high", "q75"))}
    works = sim["cost"] > 0 and target != current
    net = after["value"] - now["value"] - sim["rest_to_pay"] if works else None
    premium = {c: round((math.exp(m["class"][c]) - 1) * 100, 1) for c in LABELS} if m else None
    return {
        "current_label": current,
        "target_label": target,
        "value_now": {k: round_value(v) for k, v in now.items()},
        "value_after": {k: round_value(v) for k, v in after.items()} if works else None,
        "price_m2_now": round(market["price_per_m2"] * f_now * adj),
        "works": works,
        "cost": {"low": sim["cost_low"], "high": sim["cost_high"]},
        "aids": sim["subsidies"] + sim["cee_est"],
        "rest": {"low": sim["rest_to_pay_low"], "high": sim["rest_to_pay_high"], "value": sim["rest_to_pay"]},
        "net_gain": round_value(net) if net is not None else None,
        "class_premium": premium,
        "class_scope": (m or {}).get("scope"),
        "class_sample": (m or {}).get("n"),
        "class_period": (m or {}).get("period"),
        "adjustment_pct": adjustment_pct,
    }


class ValuationRequest(BaseModel):
    meta: ReportMeta
    simulation: SimulationInput
    adjustment_pct: float = Field(0, ge=-30, le=30)
    adjustment_note: Optional[str] = Field(None, max_length=300)
    client_name: Optional[str] = Field(None, max_length=100)


async def build(data: ValuationRequest, user: User, store: SupabaseStore) -> Dict[str, Any]:
    profile = await store.ensure_profile(user.id, user.email)
    if not is_pro(profile):
        raise HTTPException(status_code=402, detail="Réservé aux abonnés Pro.")
    meta = data.meta
    prop = data.simulation.property
    insee = meta.insee_code or prop.insee_code
    if not insee:
        raise HTTPException(status_code=400, detail="Commune inconnue pour ce logement : avis de valeur impossible.")
    market = await market_price(insee, prop.building_type, meta.latitude, meta.longitude, prop.surface)
    if not market:
        raise HTTPException(status_code=422, detail="Pas assez de ventes comparables connues autour de ce logement.")
    prop.price_per_m2 = market["price_per_m2"]
    prop.price_source = market["source"]
    prop.insee_code = insee
    sim = simulate(data.simulation)
    kind = kind_of(prop.building_type)
    result = compute(sim, market, prop.surface, kind, department(insee, prop.postcode), data.adjustment_pct)
    return {**result, "market": market, "sim": sim}


@router.post("/valuation")
async def valuation(data: ValuationRequest, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    result = await build(data, user, store)
    sim = result.pop("sim")
    result["detailed_costs"] = [{"name": d["name"], "low": d["cost_low"], "high": d["cost_high"]} for d in sim["detailed_costs"]]
    return result


@router.post("/valuation/pdf")
async def valuation_pdf(data: ValuationRequest, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    result = await build(data, user, store)
    agency = await store.get_agent_page(user.id)
    if not agency:
        raise HTTPException(status_code=409, detail="Renseignez d'abord votre agence (page Contacts).")
    meta = data.meta
    address = display_address(meta.address, meta.postcode or data.simulation.property.postcode, meta.city)
    pdf = pdf_service.generate_valuation({
        **result,
        "address": address,
        "agency": agency,
        "client_name": data.client_name,
        "adjustment_note": data.adjustment_note,
        "property": data.simulation.property.model_dump(),
        "meta": meta.model_dump(),
    })
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=Avis_de_valeur_{safe_filename(meta.address)}.pdf"})
