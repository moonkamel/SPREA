"""Prints the real format of the data sources used by build.py (run in CI)."""
import gzip
import io
import json
import sys
import urllib.request

UA = {"User-Agent": "sprea-green-value/1.0"}


def get(url, limit=None):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        print(f"GET {url} -> {r.status} {r.headers.get('content-type')} {r.headers.get('content-length')}")
        return r.read(limit) if limit else r.read()


def main():
    for year in range(2026, 2019, -1):
        try:
            raw = get(f"https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/59.csv.gz", 400_000)
            text = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(3000).decode("utf-8", "replace") if raw[:2] == b"\x1f\x8b" else raw[:3000].decode()
            print(text[:1500])
            break
        except Exception as e:
            print(year, "DVF error", type(e).__name__, e)

    base = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe"
    try:
        schema = json.loads(get(f"{base}/schema?mimeType=application/json"))
        names = [f.get("key") for f in schema] if isinstance(schema, list) else schema
        print("ADEME fields:", [n for n in names if any(k in n for k in ("ban", "adresse", "commune", "date", "etiquette", "surface", "type_bat", "periode", "annee", "geopoint", "insee", "voie", "rue", "etage", "logement"))])
    except Exception as e:
        print("schema error", type(e).__name__, e)
    try:
        page = json.loads(get(f"{base}/lines?size=3&qs=code_departement_ban:59&select=numero_dpe,date_etablissement_dpe,etiquette_dpe,type_batiment,surface_habitable_logement,code_insee_ban,numero_voie_ban,nom_rue_ban,adresse_ban,identifiant_ban,_geopoint,periode_construction,complement_adresse_logement"))
        print("ADEME total:", page.get("total"), "next:", (page.get("next") or "")[:200])
        print(json.dumps(page.get("results"), ensure_ascii=False, indent=1)[:2500])
    except Exception as e:
        print("lines error", type(e).__name__, e)
        if hasattr(e, "read"):
            print(e.read()[:500])


if __name__ == "__main__":
    sys.exit(main())
