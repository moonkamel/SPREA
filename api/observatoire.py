"""Public observatory of the green value: price gaps between DPE classes
measured on real sales (api/data/green_value.json), nationally and per
department. Aggregates only, no individual sale."""
import math
from typing import Any, Dict, Optional

from fastapi import APIRouter, Response

try:
    from api.green_value import LABELS, load
except ImportError:
    from green_value import LABELS, load

router = APIRouter(prefix="/api")

DEPARTMENTS = {
    "01": "Ain", "02": "Aisne", "03": "Allier", "04": "Alpes-de-Haute-Provence", "05": "Hautes-Alpes", "06": "Alpes-Maritimes",
    "07": "Ardèche", "08": "Ardennes", "09": "Ariège", "10": "Aube", "11": "Aude", "12": "Aveyron", "13": "Bouches-du-Rhône",
    "14": "Calvados", "15": "Cantal", "16": "Charente", "17": "Charente-Maritime", "18": "Cher", "19": "Corrèze",
    "2A": "Corse-du-Sud", "2B": "Haute-Corse", "21": "Côte-d'Or", "22": "Côtes-d'Armor", "23": "Creuse", "24": "Dordogne",
    "25": "Doubs", "26": "Drôme", "27": "Eure", "28": "Eure-et-Loir", "29": "Finistère", "30": "Gard", "31": "Haute-Garonne",
    "32": "Gers", "33": "Gironde", "34": "Hérault", "35": "Ille-et-Vilaine", "36": "Indre", "37": "Indre-et-Loire", "38": "Isère",
    "39": "Jura", "40": "Landes", "41": "Loir-et-Cher", "42": "Loire", "43": "Haute-Loire", "44": "Loire-Atlantique",
    "45": "Loiret", "46": "Lot", "47": "Lot-et-Garonne", "48": "Lozère", "49": "Maine-et-Loire", "50": "Manche", "51": "Marne",
    "52": "Haute-Marne", "53": "Mayenne", "54": "Meurthe-et-Moselle", "55": "Meuse", "56": "Morbihan", "57": "Moselle",
    "58": "Nièvre", "59": "Nord", "60": "Oise", "61": "Orne", "62": "Pas-de-Calais", "63": "Puy-de-Dôme",
    "64": "Pyrénées-Atlantiques", "65": "Hautes-Pyrénées", "66": "Pyrénées-Orientales", "67": "Bas-Rhin", "68": "Haut-Rhin",
    "69": "Rhône", "70": "Haute-Saône", "71": "Saône-et-Loire", "72": "Sarthe", "73": "Savoie", "74": "Haute-Savoie",
    "75": "Paris", "76": "Seine-Maritime", "77": "Seine-et-Marne", "78": "Yvelines", "79": "Deux-Sèvres", "80": "Somme",
    "81": "Tarn", "82": "Tarn-et-Garonne", "83": "Var", "84": "Vaucluse", "85": "Vendée", "86": "Vienne", "87": "Haute-Vienne",
    "88": "Vosges", "89": "Yonne", "90": "Territoire de Belfort", "91": "Essonne", "92": "Hauts-de-Seine",
    "93": "Seine-Saint-Denis", "94": "Val-de-Marne", "95": "Val-d'Oise", "971": "Guadeloupe", "972": "Martinique",
    "973": "Guyane", "974": "La Réunion", "976": "Mayotte",
}
KIND_KEYS = {"Maison": "maisons", "Appartement": "appartements"}
# Department figures are shown once they rest on enough sales
MIN_DEPARTMENT_SALES = 300


def pct(effect: Optional[float]) -> Optional[float]:
    return round((math.exp(effect) - 1) * 100, 1) if effect is not None else None


def build(data: Dict[str, Any]) -> Dict[str, Any]:
    national, departments = {}, {}
    for kind, key in KIND_KEYS.items():
        k = (data.get("kinds") or {}).get(kind)
        if not k:
            continue
        nat = k["national"]
        national[key] = {"sales": nat["n"], "premium": {c: pct(nat["class"][c]) for c in LABELS},
                         "mix": {c: round(nat["mix"].get(c, 0) * 100, 1) for c in LABELS}}
        for dep, d in (k.get("departments") or {}).items():
            entry = departments.setdefault(dep, {"code": dep, "name": DEPARTMENTS.get(dep, dep)})
            if "class" in d and d.get("n", 0) >= MIN_DEPARTMENT_SALES:
                entry[key] = {"sales": d["n"], "premium": {c: pct(d["class"][c]) for c in LABELS},
                              "mix": {c: round(d["mix"].get(c, 0) * 100, 1) for c in LABELS}}
    deps = sorted((d for d in departments.values() if "maisons" in d or "appartements" in d),
                  key=lambda d: (len(d["code"]) > 2, d["code"].replace("2A", "20A").replace("2B", "20B")))
    total = sum(v["sales"] for v in national.values())
    return {"period": data.get("period"), "updated": data.get("generated"), "total_sales": total,
            "national": national, "departments": deps}


@router.get("/observatoire")
async def observatoire(response: Response):
    data = load()
    if not data:
        return {"national": {}, "departments": [], "total_sales": 0}
    # Public data, changes monthly: cacheable by the CDN
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
    return build(data)
