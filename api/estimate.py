"""Public online estimator (/estimation): free, immediate, no sign-up.

Value: price per m2 of comparable DVF sales around the dwelling (api/dvf.py:
same kind, similar surface, 500 m to the commune, brought to today's prices),
brought to the dwelling's own DPE class with the class effects measured on
real sales in its department (api/green_value.py), then a few usual
adjustments (condition, floor, outdoor space, parking), each shown with its
weight. The range narrows with the agreement of the comparable sales; a
reliability score says how much to trust it.

Around it: the dwelling's DPE prefilled from the ADEME open data, a free-text
description read by Claude, a short explanation written by Claude (both with a
rule-based fallback), and the owner's request to be called back, routed with
their consent to the SPREA subscriber whose alert zone covers the address.
"""
import html
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

try:
    from api import claude
    from api.accounts import is_pro, store_dep
    from api.ademe_client import AdemeConnector
    from api.auth import User, current_user
    from api.contacts import PHONE_RE, clean, valid_email
    from api.dvf import distance_m, market_price
    from api.emailer import send_email
    from api.green_value import LABELS, WORKS_SHARE, department, model, quarter_index
    from api.ratelimit import RateLimiter, lead_limiter
    from api.store import SupabaseStore
    from api.valuation import class_factor, round_value
except ImportError:
    import claude
    from accounts import is_pro, store_dep
    from ademe_client import AdemeConnector
    from auth import User, current_user
    from contacts import PHONE_RE, clean, valid_email
    from dvf import distance_m, market_price
    from emailer import send_email
    from green_value import LABELS, WORKS_SHARE, department, model, quarter_index
    from ratelimit import RateLimiter, lead_limiter
    from store import SupabaseStore
    from valuation import class_factor, round_value

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# The page re-estimates on every change (debounced): loose, per IP
estimate_limiter = RateLimiter(max_calls=60, period_seconds=60)
# Claude calls (free-text reading, explanation): a visitor needs a handful
estimate_ai_limiter = RateLimiter(max_calls=30, period_seconds=3600)

ademe = AdemeConnector()

# Usual adjustments, in % of the value. Deliberately moderate: the comparable
# sales already carry the local level, these only move the dwelling within it
CONDITION = {"a_renover": (-12, "À rénover"), "rafraichir": (-5, "Travaux de rafraîchissement"),
             "bon": (0, "Bon état"), "refait": (6, "Refait à neuf")}
OUTDOOR = {"balcon": (2, "Balcon"), "terrasse": (4, "Terrasse"), "jardin": (5, "Jardin privatif")}
PARKING_PCT = {"appartement": 3, "maison": 2}
POOL_PCT = 4
ADJUSTMENT_RANGE = (-25, 15)
# Half-width of the range: from the spread of the comparable sales, kept between these
SPREAD_RANGE = (0.05, 0.15)
TARGET_LABEL = "C"


class EstimateRequest(BaseModel):
    address: str = Field(..., min_length=3, max_length=200)
    insee: str = Field(..., pattern=r"^[0-9][0-9AB][0-9]{3}$")
    postcode: Optional[str] = Field(None, pattern=r"^[0-9]{5}$")
    city: Optional[str] = Field(None, max_length=80)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    kind: Literal["appartement", "maison"]
    surface: float = Field(..., ge=9, le=1000)
    rooms: Optional[int] = Field(None, ge=1, le=20)
    land: Optional[float] = Field(None, ge=0, le=100000)
    floor: Optional[int] = Field(None, ge=0, le=60)
    elevator: Optional[bool] = None
    outdoor: List[Literal["balcon", "terrasse", "jardin"]] = []
    parking: bool = False
    pool: bool = False
    condition: Literal["a_renover", "rafraichir", "bon", "refait"] = "bon"
    dpe: Optional[Literal["A", "B", "C", "D", "E", "F", "G"]] = None
    year: Optional[int] = Field(None, ge=1500, le=2100)


def adjustments(d: EstimateRequest) -> List[Dict[str, Any]]:
    """Each usual adjustment that applies, with its weight in %."""
    out: List[Dict[str, Any]] = []
    pct, label = CONDITION[d.condition]
    if pct:
        out.append({"label": label, "pct": pct})
    if d.kind == "appartement" and d.floor is not None:
        if d.floor == 0:
            out.append({"label": "Rez-de-chaussée", "pct": -6})
        elif d.floor >= 3 and d.elevator is False:
            out.append({"label": f"{d.floor}e étage sans ascenseur", "pct": -9 if d.floor >= 5 else -6})
        elif d.floor >= 4 and d.elevator:
            out.append({"label": "Étage élevé avec ascenseur", "pct": 3})
    # Outdoor space: the best one counts, not the sum
    best = max((OUTDOOR[o] for o in d.outdoor if not (o == "jardin" and d.kind == "maison")), default=None)
    if best:
        out.append({"label": best[1], "pct": best[0]})
    if d.parking:
        out.append({"label": "Stationnement", "pct": PARKING_PCT[d.kind]})
    if d.pool and d.kind == "maison":
        out.append({"label": "Piscine", "pct": POOL_PCT})
    return out


def reliability(market: Dict[str, Any], spread: float, dpe_known: bool) -> Dict[str, Any]:
    """1 to 5 from the number of comparable sales, how close they are, whether
    their surface matches and how much they agree."""
    score = 1
    n = market.get("sales") or 0
    score += 1 if n >= 20 else 0
    score += 1 if n >= 50 else 0
    scope = market.get("scope") or ""
    near = "à moins de" in scope and not market.get("wide") and not re.search(r"\b[2-9] km|\b1\d km", scope)
    score += 1 if near else 0
    score += 1 if market.get("surface_matched") and spread <= 0.12 else 0
    # Without the DPE class, the value can be off by the class effect: never "very high"
    score = min(score, 5 if dpe_known else 4)
    label = {5: "Très élevée", 4: "Élevée", 3: "Bonne", 2: "Moyenne", 1: "Indicative"}[score]
    return {"score": score, "label": label}


def trend(kind: str, dep: Optional[str]) -> Optional[Dict[str, Any]]:
    """Price change over the last four quarters measured (department index)."""
    index = quarter_index("Maison" if kind == "maison" else "Appartement", dep)
    if not index or len(index) < 5:
        return None
    quarters = sorted(index)
    latest, before = quarters[-1], quarters[-5]
    # index[q] is the log gap between quarter q and the latest one
    pct = (math.exp(index[latest] - index[before]) - 1) * 100
    return {"pct": round(pct, 1), "from": before, "to": latest}


def compute(d: EstimateRequest, market: Dict[str, Any]) -> Dict[str, Any]:
    kind = "Maison" if d.kind == "maison" else "Appartement"
    dep = department(d.insee, d.postcode)
    m = model(kind, dep)
    f_class = class_factor(m, d.dpe) if d.dpe else 1.0
    adj = adjustments(d)
    total = max(ADJUSTMENT_RANGE[0], min(ADJUSTMENT_RANGE[1], sum(a["pct"] for a in adj)))
    median = market["price_per_m2"]
    price_m2 = median * f_class * (1 + total / 100)
    value = price_m2 * d.surface
    iqr = (market["q75"] - market["q25"]) / (2 * median) if median else 0.15
    spread = max(SPREAD_RANGE[0], min(SPREAD_RANGE[1], iqr * 0.55))
    dpe_effect = round((f_class - 1) * 100, 1) if d.dpe else None
    # Potential after an energy renovation, for the worst classes (same prudence as the reports)
    renovation = None
    if d.dpe in ("E", "F", "G") and m:
        gain = value * (class_factor(m, TARGET_LABEL) / f_class - 1) * WORKS_SHARE
        if gain > 0:
            renovation = {"target": TARGET_LABEL, "gain": round_value(gain)}
    rel = reliability(market, spread, bool(d.dpe))
    return {
        "value": round_value(value),
        "low": round_value(value * (1 - spread)),
        "high": round_value(value * (1 + spread)),
        "price_m2": round(price_m2),
        "market_m2": median,
        "market_q25": market["q25"],
        "market_q75": market["q75"],
        "dpe_effect": dpe_effect,
        "adjustments": adj,
        "adjustment_total": total,
        "reliability": rel,
        "trend": trend(d.kind, dep),
        "renovation": renovation,
        "sales": market.get("sales"),
        "scope": market.get("scope"),
        "period": market.get("period"),
        "source": market.get("source"),
        "comparables": market.get("comparables", [])[:6],
    }


@router.post("/estimate", dependencies=[Depends(estimate_limiter)])
async def estimate(d: EstimateRequest):
    market = await market_price(d.insee, "Maison" if d.kind == "maison" else "Appartement", d.lat, d.lon, d.surface)
    if not market:
        raise HTTPException(status_code=422, detail="Pas assez de ventes comparables connues autour de cette adresse pour estimer ce bien.")
    return compute(d, market)


# --- DPE of the address (ADEME open data), to prefill the form ---

@router.get("/estimate/dpe", dependencies=[Depends(estimate_limiter)])
async def estimate_dpe(q: str):
    """DPE published at this address: kind, surface, year, label. Several for a
    block of flats; the page lets the owner pick theirs."""
    q = (q or "").strip()
    if not 5 <= len(q) <= 200:
        raise HTTPException(status_code=400, detail="Adresse invalide.")
    try:
        found = await ademe.search_by_address(q)
    except Exception as e:  # noqa: BLE001 - the prefill is optional
        logger.error(f"Estimator DPE lookup failed: {type(e).__name__}")
        found = []
    out, seen = [], set()
    for p in found:
        kind = (p.building_type or "").lower()
        kind = "maison" if "maison" in kind else "appartement" if "appart" in kind else None
        surface = round(p.shab) if p.shab else None
        label = p.dpe_class_current.value if p.dpe_class_current else None
        if not kind or not surface:
            continue
        key = (kind, surface, label)
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "surface": surface, "dpe": label, "year": p.construction_year,
                    "date": p.date_etablissement})
        if len(out) >= 8:
            break
    return {"results": out}


# --- Free-text description read by Claude ---

class ParseRequest(BaseModel):
    text: str = Field(..., min_length=3, max_length=1500)


PARSE_SCHEMA = claude.strict_schema({
    "type": "object",
    "properties": {
        "kind": claude.nullable({"type": "string", "enum": ["appartement", "maison"]}),
        "surface": claude.nullable({"type": "number"}),
        "rooms": claude.nullable({"type": "integer"}),
        "land": claude.nullable({"type": "number"}),
        "floor": claude.nullable({"type": "integer"}),
        "elevator": claude.nullable({"type": "boolean"}),
        "outdoor": {"type": "array", "items": {"type": "string", "enum": ["balcon", "terrasse", "jardin"]}},
        "parking": claude.nullable({"type": "boolean"}),
        "pool": claude.nullable({"type": "boolean"}),
        "condition": claude.nullable({"type": "string", "enum": ["a_renover", "rafraichir", "bon", "refait"]}),
        "dpe": claude.nullable({"type": "string", "enum": list(LABELS)}),
        "year": claude.nullable({"type": "integer"}),
    },
})

PARSE_SYSTEM = (
    "Tu lis la description d'un logement écrite par son propriétaire ou copiée d'une annonce, en français, et tu "
    "remplis les champs d'un formulaire d'estimation. Ne remplis un champ que si le texte le dit ou l'implique "
    "clairement ; sinon null (ou liste vide). Repères : T3/F3 = 3 pièces ; « RDC » = étage 0 ; « refait à neuf », "
    "« rénové récemment » = refait ; « travaux à prévoir », « à rafraîchir » = rafraichir ; « à rénover entièrement », "
    "« gros travaux » = a_renover ; « garage », « place de parking », « box » = parking ; land = surface du terrain "
    "en m² (maison) ; dpe = lettre de l'étiquette énergie si citée.")


def parse_rules(text: str) -> Dict[str, Any]:
    """Fallback without Claude: the obvious patterns."""
    t = text.lower()
    out: Dict[str, Any] = {"outdoor": []}
    if re.search(r"\bmaison|villa|pavillon|longère|corps de ferme", t):
        out["kind"] = "maison"
    elif re.search(r"\bappart|\bstudio|\bt[1-9]\b|\bf[1-9]\b|duplex|loft", t):
        out["kind"] = "appartement"
    m = re.search(r"(\d{2,4}(?:[.,]\d)?)\s*(?:m²|m2|mètres carrés|metres carres)(?!\s*de\s*terrain)", t)
    if m:
        out["surface"] = float(m.group(1).replace(",", "."))
    m = re.search(r"\b[tf]([1-9])\b|(\d{1,2})\s*pi[eè]ces", t)
    if m:
        out["rooms"] = int(m.group(1) or m.group(2))
    if "studio" in t:
        out["rooms"] = 1
    m = re.search(r"(\d{2,6})\s*(?:m²|m2)\s*de\s*terrain|terrain\s*(?:de\s*)?(\d{2,6})", t)
    if m:
        out["land"] = float(m.group(1) or m.group(2))
    if re.search(r"\brdc\b|rez[- ]de[- ]chauss", t):
        out["floor"] = 0
    else:
        m = re.search(r"(\d{1,2})\s*(?:e|ème|eme|er)\s*étage", t)
        if m:
            out["floor"] = int(m.group(1))
    if "sans ascenseur" in t:
        out["elevator"] = False
    elif "ascenseur" in t:
        out["elevator"] = True
    for word in ("balcon", "terrasse", "jardin"):
        if word in t:
            out["outdoor"].append(word)
    if re.search(r"parking|garage|\bbox\b|stationnement", t):
        out["parking"] = True
    if "piscine" in t:
        out["pool"] = True
    if re.search(r"refait à neuf|entièrement rénové|rénové récemment|neuf\b", t):
        out["condition"] = "refait"
    elif re.search(r"gros travaux|à rénover|a renover", t):
        out["condition"] = "a_renover"
    elif re.search(r"rafra[iî]chi|travaux à prévoir", t):
        out["condition"] = "rafraichir"
    m = re.search(r"(?:dpe|classe énergie|étiquette)\s*:?\s*([a-g])\b", t)
    if m:
        out["dpe"] = m.group(1).upper()
    return out


@router.post("/estimate/parse", dependencies=[Depends(estimate_ai_limiter)])
async def estimate_parse(data: ParseRequest):
    try:
        fields = await claude.json_call(PARSE_SYSTEM, data.text, PARSE_SCHEMA, model=claude.FAST_MODEL,
                                        effort="low", max_tokens=2000, timeout=25, fallback=False)
        source = "ia"
    except claude.ClaudeUnavailable:
        fields, source = parse_rules(data.text), "regles"
    fields = {k: v for k, v in fields.items() if v not in (None, [], "")}
    if "surface" in fields and not 9 <= fields["surface"] <= 1000:
        fields.pop("surface")
    return {"fields": fields, "source": source}


# --- Short explanation written by Claude ---

class ExplainRequest(BaseModel):
    city: Optional[str] = Field(None, max_length=80)
    kind: Literal["appartement", "maison"]
    surface: float = Field(..., ge=9, le=1000)
    value: int = Field(..., ge=1000, le=100_000_000)
    low: int
    high: int
    price_m2: int
    market_m2: int
    sales: Optional[int] = None
    scope: Optional[str] = Field(None, max_length=200)
    dpe: Optional[str] = Field(None, max_length=1)
    dpe_effect: Optional[float] = None
    adjustments: List[Dict[str, Any]] = Field(default=[], max_length=10)
    trend_pct: Optional[float] = None
    reliability: Optional[str] = Field(None, max_length=30)


EXPLAIN_SCHEMA = claude.strict_schema({"type": "object", "properties": {"text": {"type": "string"}}})

EXPLAIN_SYSTEM = (
    "Tu expliques une estimation immobilière à son propriétaire, en français, en 3 ou 4 phrases simples et "
    "chaleureuses (90 mots au plus). Appuie-toi uniquement sur les chiffres fournis : prix médian des ventes "
    "comparables, effet de l'étiquette énergie, ajustements, tendance du marché. N'invente aucun chiffre, aucune "
    "caractéristique, aucun conseil juridique ou fiscal. Termine par une phrase rappelant qu'une visite par un "
    "professionnel du secteur affine le prix (état réel, vue, exposition, copropriété). Pas de titre, pas de liste.")


def fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ")


def explain_rules(d: ExplainRequest) -> str:
    what = "cette maison" if d.kind == "maison" else "cet appartement"
    parts = [f"Les ventes comparables {d.scope or 'du secteur'} se sont faites autour de {fmt(d.market_m2)} € le m²"
             + (f" ({d.sales} ventes)" if d.sales else "") + "."]
    if d.dpe and d.dpe_effect:
        parts.append(f"Son étiquette {d.dpe} {'valorise' if d.dpe_effect > 0 else 'pèse sur'} le prix d'environ "
                     f"{abs(d.dpe_effect):.0f} % par rapport aux logements voisins.")
    moves = [a for a in d.adjustments if a.get("pct")]
    if moves:
        parts.append("Nous avons tenu compte de : " + ", ".join(f"{str(a.get('label', '')).lower()} ({a['pct']:+d} %)"
                                                                for a in moves) + ".")
    parts.append(f"Cela situe {what} entre {fmt(d.low)} € et {fmt(d.high)} €. Une visite par un professionnel du secteur "
                 "permet d'affiner ce prix selon l'état réel, la vue et l'exposition.")
    return " ".join(parts)


@router.post("/estimate/explain", dependencies=[Depends(estimate_ai_limiter)])
async def estimate_explain(d: ExplainRequest):
    facts = d.model_dump()
    try:
        out = await claude.json_call(EXPLAIN_SYSTEM, str(facts), EXPLAIN_SCHEMA, model=claude.FAST_MODEL,
                                     effort="low", max_tokens=1500, timeout=25, fallback=False)
        text = (out.get("text") or "").strip()
        if 40 <= len(text) <= 900:
            return {"text": text, "source": "ia"}
    except claude.ClaudeUnavailable:
        pass
    return {"text": explain_rules(d), "source": "regles"}


# --- The owner's request to be called back ---

PROJECTS = {"vendre_3m": "Vendre dans les 3 mois", "vendre_12m": "Vendre dans l'année",
            "reflexion": "En réflexion", "curiosite": "Simple curiosité"}
CONSENT_TEXT = ("J'accepte d'être recontacté(e) par téléphone ou par email au sujet de mon projet par un conseiller "
                "immobilier partenaire de SPREA exerçant dans mon secteur, à qui mes coordonnées et les informations "
                "de mon estimation sont transmises. Je peux retirer ce consentement à tout moment.")


class LeadRequest(BaseModel):
    estimate: EstimateRequest
    value: Optional[int] = Field(None, ge=0, le=100_000_000)
    low: Optional[int] = Field(None, ge=0, le=100_000_000)
    high: Optional[int] = Field(None, ge=0, le=100_000_000)
    name: str = Field(..., min_length=2, max_length=80)
    phone: Optional[str] = Field(None, max_length=25)
    email: Optional[str] = Field(None, max_length=200)
    project: Literal["vendre_3m", "vendre_12m", "reflexion", "curiosite"]
    consent: bool
    source: Optional[str] = Field(None, max_length=200)
    website: Optional[str] = None  # Honeypot: humans leave it empty

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v):
        v = (v or "").strip() or None
        if v and not PHONE_RE.match(v):
            raise ValueError("Numéro de téléphone invalide.")
        return v

    _email = field_validator("email")(lambda cls, v: valid_email(v))


async def advisor_for(store: SupabaseStore, lat: Optional[float], lon: Optional[float]) -> Optional[Dict[str, Any]]:
    """The subscriber whose active alert zone covers the address, the closest
    zone centre first: one advisor per request."""
    if lat is None or lon is None:
        return None
    zones = await store.active_zones()
    covering = sorted((distance_m(lat, lon, z["lat"], z["lon"]), z) for z in zones
                      if distance_m(lat, lon, z["lat"], z["lon"]) <= z["radius_m"])
    checked = set()
    for _, z in covering:
        uid = z["user_id"]
        if uid in checked:
            continue
        checked.add(uid)
        profile = await store.get_profile(uid)
        if is_pro(profile):
            return {"user_id": uid, "email": (profile or {}).get("email")}
    return None


def lead_email(row: Dict[str, Any], unassigned: bool = False) -> Dict[str, str]:
    """To the advisor whose zone covers the address, or to SPREA when no zone does."""
    e = html.escape
    kind = "Maison" if row["kind"] == "maison" else "Appartement"
    d = row.get("details") or {}
    value = f"{fmt(row['value'])} €" if row.get("value") else "–"
    if row.get("low") and row.get("high"):
        value += f" (entre {fmt(row['low'])} € et {fmt(row['high'])} €)"
    condition = {"a_renover": "à rénover", "rafraichir": "à rafraîchir", "bon": "bon état", "refait": "refait à neuf"}.get(d.get("condition"), "")
    bien = ", ".join(x for x in [f"{kind} de {fmt(row['surface'])} m²", f"{d['rooms']} pièces" if d.get("rooms") else "",
                                 f"DPE {d['dpe']}" if d.get("dpe") else "", condition] if x)
    lines = [("Projet", PROJECTS[row["project"]]), ("Bien", bien), ("Adresse", row["address"]),
             ("Estimation en ligne", value), ("Nom", row["name"]), ("Téléphone", row.get("phone") or "–"),
             ("Email", row.get("email") or "–")]
    if row.get("lat") is not None and row.get("lon") is not None:
        lines.append(("Carte", f"https://www.openstreetmap.org/?mlat={row['lat']}&mlon={row['lon']}#map=17/{row['lat']}/{row['lon']}"))
    rows = "".join(f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280;vertical-align:top'>{e(k)}</td><td style='padding:4px 0'>"
                   + (f"<a href='{e(v)}'>Voir sur la carte</a>" if k == "Carte" else f"<b>{e(str(v))}</b>") + "</td></tr>"
                   for k, v in lines)
    if unassigned:
        intro = ("Un propriétaire vient d'estimer son bien sur sprea.app et demande à être recontacté, mais aucun abonné "
                 "n'a de zone d'alerte qui couvre cette adresse.")
        outro = ("Il a accepté d'être recontacté par un conseiller immobilier partenaire de SPREA exerçant dans son secteur : "
                 "vous pouvez transmettre cette demande à un conseiller du secteur.")
        subject = f"Vendeur sans conseiller à {row.get('city') or 'une commune non couverte'} : {kind.lower()} de {fmt(row['surface'])} m²"
    else:
        intro = "Un propriétaire de votre secteur vient d'estimer son bien sur sprea.app et demande à être recontacté."
        outro = ("Il a donné son accord pour être appelé. Retrouvez la demande dans "
                 "<a href='https://sprea.app/contacts'>Contacts</a>.")
        subject = f"Nouveau vendeur à {row.get('city') or 'votre secteur'} : {kind.lower()} de {fmt(row['surface'])} m²"
    body = (f"<div style='font-family:Arial,sans-serif;font-size:15px;color:#1f2937'><p>Bonjour,</p><p>{e(intro)}</p>"
            f"<table>{rows}</table><p>{outro if not unassigned else e(outro)}</p><p>L'équipe SPREA</p></div>")
    text = intro + "\n\n" + "\n".join(f"{k} : {v}" for k, v in lines)
    return {"subject": subject, "html": body, "text": text}


@router.post("/estimate/lead", dependencies=[Depends(lead_limiter)])
async def estimate_lead(data: LeadRequest, store: SupabaseStore = Depends(store_dep)):
    if data.website:
        return {"received": True}  # Bot: silently ignored
    if not data.consent:
        raise HTTPException(status_code=400, detail="Cochez la case pour accepter d'être recontacté.")
    if not data.phone and not data.email:
        raise HTTPException(status_code=400, detail="Indiquez un téléphone ou un email.")
    d = data.estimate
    advisor = await advisor_for(store, d.lat, d.lon)
    row = {
        "address": clean(d.address, 200), "postcode": d.postcode, "insee": d.insee, "city": clean(d.city, 80),
        "lat": d.lat, "lon": d.lon, "kind": d.kind, "surface": d.surface,
        "details": d.model_dump(exclude={"address", "insee", "postcode", "city", "lat", "lon", "kind", "surface"}),
        "value": data.value, "low": data.low, "high": data.high,
        "name": clean(data.name, 80), "phone": data.phone, "email": data.email, "project": data.project,
        "consent_text": CONSENT_TEXT, "consent_at": datetime.now(timezone.utc).isoformat(),
        "source": clean(data.source, 200), "assigned_user_id": advisor["user_id"] if advisor else None,
    }
    await store.create_estimate_lead(row)
    if advisor and advisor.get("email"):
        mail = lead_email(row)
        await send_email(advisor["email"], mail["subject"], mail["html"], mail["text"])
    elif not advisor:
        # No subscriber covers the address: SPREA gets it, to pass on to an advisor of the area
        to = (os.getenv("LEADS_TO") or os.getenv("QUOTES_TO") or "").strip()
        if to:
            mail = lead_email(row, unassigned=True)
            await send_email(to, mail["subject"], mail["html"], mail["text"])
    logger.info(f"Estimator lead received ({'assigned' if advisor else 'unassigned'})")
    return {"received": True, "assigned": bool(advisor)}


# --- Advisor: requests received from the estimator ---

class EstimateLeadUpdate(BaseModel):
    status: str = Field(..., pattern="^(new|contacted|closed)$")


@router.get("/estimate-leads")
async def list_estimate_leads(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    return {"leads": await store.list_estimate_leads(user.id)}


@router.patch("/estimate-leads/{lead_id}")
async def update_estimate_lead(lead_id: str, data: EstimateLeadUpdate, user: User = Depends(current_user),
                               store: SupabaseStore = Depends(store_dep)):
    if not await store.update_estimate_lead(user.id, lead_id, {"status": data.status}):
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    return {"updated": True}
