"""Rent per m2 of a commune, from the "Carte des loyers" (ANIL / ministère du
Logement, data.gouv.fr, Licence Ouverte): predicted asking rent, charges
included, for an apartment or a house, per commune, with its 95 % range.

The files are found through the data.gouv.fr API (their URLs change each
year) and kept in memory a day. None when the source does not answer: the
opportunity scan then shows no yield rather than an invented one.
"""
import asyncio
import csv
import io
import logging
import time
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Most recent edition first; an older one serves while the new one is missing
DATASETS = ["693aa2feed1bf4da603faa49", "6751be987c09f4be821c6934"]
API_URL = "https://www.data.gouv.fr/api/1/datasets/{id}/"
CACHE_TTL = 24 * 3600
# kind -> {insee: (rent per m2, low, high)}
_tables: Dict[str, Tuple[float, Dict[str, Tuple[float, float, float]]]] = {}
# One download per kind when a scan asks for many dwellings at once
_locks: Dict[str, asyncio.Lock] = {}


def _number(value: Optional[str]) -> Optional[float]:
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def parse(text: str) -> Dict[str, Tuple[float, float, float]]:
    """INSEE code -> (rent per m2, low, high). Columns as published since 2022:
    INSEE_C, loypredm2, lwr.IPm2, upr.IPm2 (";" separated, decimal comma)."""
    sample = text[:2000]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fields = {f.lower().strip('"'): f for f in reader.fieldnames or []}
    insee_col = next((fields[k] for k in fields if k.startswith("insee")), None)
    rent_col = next((fields[k] for k in fields if k.startswith("loypredm2")), None)
    low_col = next((fields[k] for k in fields if k.startswith("lwr")), None)
    high_col = next((fields[k] for k in fields if k.startswith("upr")), None)
    if not insee_col or not rent_col:
        return {}
    out = {}
    for row in reader:
        code = (row.get(insee_col) or "").strip().zfill(5)
        rent = _number(row.get(rent_col))
        if len(code) == 5 and rent and 3 <= rent <= 60:
            out[code] = (rent, _number(row.get(low_col)) or rent, _number(row.get(high_col)) or rent)
    return out


def pick(resources: List[Dict], kind: str) -> Optional[str]:
    """The file for all apartments ("app", not the T1-T2 or T3+ split) or houses ("mai")."""
    want = "mai" if kind == "maison" else "app"
    for r in resources:
        name = f"{r.get('title') or ''} {r.get('url') or ''}".lower()
        if (r.get("format") or "").lower() != "csv" and ".csv" not in name:
            continue
        if want == "app" and ("app12" in name or "app3" in name or "t1" in name or "t3" in name):
            continue
        if f"-{want}-" in name or f"_{want}_" in name or f"pred-{want}" in name or f"{want}." in name:
            return r.get("url")
    return None


async def _load(kind: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Tuple[float, float, float]]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, transport=transport) as client:
        for dataset in DATASETS:
            try:
                res = await client.get(API_URL.format(id=dataset))
                if res.status_code != 200:
                    continue
                url = pick(res.json().get("resources") or [], kind)
                if not url:
                    continue
                file = await client.get(url)
                file.raise_for_status()
                content = file.content
                try:
                    text = content.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = content.decode("latin-1")
                table = parse(text)
                if table:
                    return table
            except (httpx.HTTPError, ValueError) as e:
                logger.warning(f"Rent data {dataset} unavailable: {type(e).__name__}")
    return {}


async def rent_per_m2(insee: Optional[str], building_type: Optional[str],
                      transport: Optional[httpx.AsyncBaseTransport] = None) -> Optional[Dict[str, float]]:
    """{"rent_m2", "low", "high"} for this commune and kind of dwelling, or None."""
    code = (insee or "").strip().upper()
    if len(code) != 5:
        return None
    kind = "maison" if "maison" in (building_type or "").lower() else "appartement"
    cached = _tables.get(kind)
    if not cached or time.time() - cached[0] > CACHE_TTL:
        async with _locks.setdefault(kind, asyncio.Lock()):
            cached = _tables.get(kind)
            if not cached or time.time() - cached[0] > CACHE_TTL:
                table = await _load(kind, transport)
                # An empty table is kept an hour only: the source may come back
                _tables[kind] = (time.time() - (CACHE_TTL - 3600 if not table else 0), table)
                cached = _tables[kind]
    found = cached[1].get(code)
    if not found:
        return None
    return {"rent_m2": found[0], "low": found[1], "high": found[2]}
