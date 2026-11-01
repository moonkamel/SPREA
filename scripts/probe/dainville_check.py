"""One-off check: valuation of 13 avenue Jean Mermoz, Dainville (sold
174,500 EUR) and how house prices per m2 move with the land area."""
import asyncio
import csv
import io
import statistics
import sys
from datetime import date

import httpx

sys.path.insert(0, ".")
from api import dvf  # noqa: E402
from api.ademe_client import AdemeConnector  # noqa: E402
from api.cadastre import find_parcel  # noqa: E402


async def main():
    props = await AdemeConnector().search_by_address("13 avenue Jean Mermoz 62000 Dainville")
    for p in props[:4]:
        print("DPE", p.ademe_dpe_number, p.address, p.building_type, p.shab, p.dpe_class_current, p.latitude, p.longitude, p.insee_code)
    if not props:
        return
    p = props[0]
    market = await dvf.market_price(p.insee_code, p.building_type, p.latitude, p.longitude, p.shab)
    print("MARKET", {k: market.get(k) for k in ("price_per_m2", "q25", "q75", "sales", "scope", "period")} if market else None)
    if market:
        print("VALUE", round(market["price_per_m2"] * p.shab))
    parcel = await find_parcel(p.latitude, p.longitude)
    print("PARCEL", parcel)
    # House sales of the commune with their land
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        rows = []
        for year in range(2026, 2019, -1):
            r = await c.get(dvf.DVF_URL.format(year=year, dep="62", insee=p.insee_code))
            if r.status_code != 200:
                continue
            muts = {}
            for row in csv.DictReader(io.StringIO(r.text)):
                if row.get("nature_mutation") == "Vente":
                    muts.setdefault(row["id_mutation"], []).append(row)
            for ms in muts.values():
                houses = [m for m in ms if m.get("type_local") == "Maison"]
                if len({m.get("surface_reelle_bati") for m in houses}) != 1 or any(m.get("type_local") == "Appartement" for m in ms):
                    continue
                land = sum({(m.get("id_parcelle"), m.get("nature_culture"), m.get("surface_terrain")): float(m.get("surface_terrain") or 0) for m in ms}.values())
                h = houses[0]
                price, surf = float(h["valeur_fonciere"] or 0), float(h["surface_reelle_bati"] or 0)
                if price and surf >= 30:
                    rows.append((year, h["date_mutation"], h.get("adresse_numero"), h.get("adresse_nom_voie"), surf, land, price, price / surf))
    print("SALES", len(rows))
    for lo, hi in ((0, 150), (150, 300), (300, 500), (500, 800), (800, 100000)):
        b = [r[7] for r in rows if lo <= r[5] < hi and r[0] >= 2023]
        if b:
            print(f"LAND {lo}-{hi} m2: {len(b)} ventes 2023+, median {round(statistics.median(b))} EUR/m2")
    for r in rows:
        if "MERMOZ" in (r[3] or "").upper():
            print("MERMOZ", r)


asyncio.run(main())
