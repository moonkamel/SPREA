"""Explore the ADEME DPE dataset used by api/ademe_client.py.

    python scripts/ademe_fields.py                  # every field name and title
    python scripts/ademe_fields.py isolation        # fields matching a word
    python scripts/ademe_fields.py --sample         # one full record
    python scripts/ademe_fields.py --dpe 2259E0123456X

Useful to check that the fields mapped in AdemeConnector._map_to_internal
(deperditions_*, qualite_isolation_*, conso_5_usages_par_m2_ef...) exist.
"""
import json
import sys

import httpx

DATASET = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe"


def main(args):
    with httpx.Client(timeout=20) as client:
        if args and args[0] == "--sample":
            print(json.dumps(client.get(f"{DATASET}/lines", params={"size": 1}).json()["results"][0], indent=2, ensure_ascii=False))
        elif len(args) == 2 and args[0] == "--dpe":
            res = client.get(f"{DATASET}/lines", params={"q": args[1], "q_fields": "numero_dpe", "size": 1}).json()
            print(json.dumps(res["results"][0] if res.get("results") else None, indent=2, ensure_ascii=False))
        else:
            word = args[0].lower() if args else ""
            for field in client.get(f"{DATASET}/schema").json():
                name = field.get("key") or field.get("name") or ""
                if word in name.lower() or word in (field.get("title") or "").lower():
                    print(f"{name:55} {field.get('title') or ''}")


if __name__ == "__main__":
    main(sys.argv[1:])
