"""Live check of the investor scan on real data (ADEME, DVF, Carte des
loyers): ranks an area and writes the investment file of the best ones to
reports/ (rule-based thesis, no AI).

  python scripts/audit/opportunities_live.py 3.04,50.62,3.08,50.65 [marchand|bailleur]
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api import opportunities  # noqa: E402
from api.pdf_service import pdf_service  # noqa: E402
from api.rents import rent_per_m2  # noqa: E402
from api.report_content import display_address  # noqa: E402
from scripts.audit.checks import pdf_text  # noqa: E402


async def main(bbox: str, profile: str):
    print("Loyer Lille (appartement):", await rent_per_m2("59350", "appartement"))
    res = await opportunities.scan(bbox, ["E", "F", "G"], None, profile)
    print(f"{res['analysed']} DPE analysés, {res['valued']} chiffrés, {res['positive']} avec marge, total zone {res['total']}")
    for i, o in enumerate(res["items"][:15], 1):
        print(f"{i:2}. {o['address'][:45]:45} {o['kind'][:5]} {o['surface']:6.1f} m² {o['label']}→{o['new_label']} "
              f"achat {o['price']:>9,.0f} budget {o['total']:>9,.0f} revente {o['resale']:>9,.0f} marge {o['margin']:>+9,.0f} "
              f"({o['margin_pct']} %) loyer {o.get('rent_month')} rdt {o.get('gross_yield')}")
    os.makedirs("reports", exist_ok=True)
    for o in res["items"][:3]:
        full = await opportunities.analyse({"numero_dpe": o["number"]} | (await raw_of(o["number"])), profile)
        thesis = {**opportunities.fallback_thesis(opportunities.public(full), profile), "source": "rules"}
        pdf = pdf_service.generate_investment({
            **opportunities.public(full), "profile": profile, "profile_name": opportunities.PROFILES[profile]["name"],
            "notary_rate": opportunities.PROFILES[profile]["notary"], "thesis": thesis, "agency": {"agency_name": "Agence test"},
            "address": display_address(full["address"], full.get("postcode"), full.get("city")),
            "valuation": full["_v"], "sim": full["_sim"], "market": full["_market"]})
        path = f"reports/dossier_{o['number']}.pdf"
        open(path, "wb").write(pdf)
        open(path.replace(".pdf", ".txt"), "w").write(pdf_text(pdf))
        print("écrit", path)


async def raw_of(number: str):
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(opportunities.ADEME_URL, params={"qs": f'numero_dpe:"{number}"', "size": "1"})
        return res.json()["results"][0]


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "marchand"))
