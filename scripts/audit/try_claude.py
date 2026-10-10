"""Live check of the Claude features on fictitious data (CI, with the
ANTHROPIC_API_KEY secret): the document reader on a sample PV d'AG, and the
reading of sale signals. Prints the results; nothing is stored."""
import asyncio
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api import claude, copro_docs, sale_signals  # noqa: E402
from scripts.audit.sample_pv import main as make_pv  # noqa: E402


async def run():
    if not claude.configured():
        print("ANTHROPIC_API_KEY absent : rien à tester.")
        return
    make_pv("pv.pdf")
    data = open("pv.pdf", "rb").read()
    files = [{"name": "PV_AG_2025.pdf", "type": "application/pdf"}]
    result = await claude.json_call(copro_docs.SYSTEM, copro_docs.build_content(files, [data], "14 rue des Arts 59800 Lille", date.today()),
                                    copro_docs.SCHEMA, effort="medium", max_tokens=16000)
    result = copro_docs.clean(result)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    text = json.dumps(result, ensure_ascii=False)
    for name in ("Fictif", "Anne Exemple"):
        print(f"Nom '{name}' repris : {'OUI (à corriger)' if name in text else 'non'}")
    open("result.json", "w").write(text)
    signal = {"events": [{"date": "2026-09-01", "kind": "liquidation_judiciaire", "label": "Liquidation judiciaire"},
                         {"date": "2025-03-01", "kind": "dirigeant", "label": "Changement de dirigeant"}]}
    print(json.dumps(await sale_signals.explain(signal, {"nb_log": 8, "year_built": 1930, "dpe_label": "F", "dpe_fg": 5,
                                                         "last_sale_date": "1998-06-01", "legal_form": "SCI", "portfolio_count": 2},
                                                date.today()), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(run())
