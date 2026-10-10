"""Default works and result of each dwelling, for the before/after comparison
of a change (run once in each checkout, on the same DPE read by the audit).

  python scripts/audit/selection.py properties.json selection.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api.ademe_client import PropertySchema  # noqa: E402
from api.main import enrich_property, simulation_property  # noqa: E402
from api.simulation import SimulationInput, simulate  # noqa: E402


def main(src: str, dst: str):
    out = {}
    for raw in json.load(open(src)):
        number = raw.get("ademe_dpe_number") or raw.get("numero_dpe") or raw.get("dpe_number")
        try:
            prop = PropertySchema.model_validate(raw)
            enriched = enrich_property(prop)
            works = enriched.get("preselected_works") or []
            sim = simulate(SimulationInput(property=simulation_property(prop), works=works))
            out[number] = {"works": works, "suggested": enriched.get("suggested_works") or [], "label": sim["current_label"],
                           "new_label": sim["new_label"], "cost": round(sim["cost"]), "rest": round(sim["rest_to_pay"]),
                           "aids": round(sim["subsidies"] + sim["cee_est"]), "pathway": sim["aid_pathway"],
                           "kind": prop.building_type, "surface": prop.shab}
        except Exception as e:  # noqa: BLE001 - one bad record must not stop the comparison
            out[number] = {"error": f"{type(e).__name__}: {e}"}
    json.dump(out, open(dst, "w"), ensure_ascii=False)
    print(f"{len(out)} logements")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
