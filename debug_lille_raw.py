import httpx
import asyncio
import json

async def debug_lille():
    dataset_id = "meg-83tjwtg8dyz4vv7h1dqe"
    url = f"https://data.ademe.fr/data-fair/api/v1/datasets/{dataset_id}/lines"
    params = {
        "q": "43 Brule Maison",
        "qs": 'code_postal_brut:"59000"',
        "size": 5
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        data = r.json()
        print(f"Total: {data.get('total')}")
        for res in data.get("results", []):
            print("\n--- Record ---")
            # Print only relevant fields for debugging
            for k in ["adresse_brut", "numero_dpe", "surface_habitable_logement", "etiquette_dpe", "date_etablissement_dpe", "numero_voie_ban", "nom_rue_ban"]:
                print(f"{k}: {res.get(k)}")

if __name__ == "__main__":
    asyncio.run(debug_lille())
