import httpx
import asyncio
import json

async def test_hyper_precision():
    dataset_id = "meg-83tjwtg8dyz4vv7h1dqe"
    url = f"https://data.ademe.fr/data-fair/api/v1/datasets/{dataset_id}/lines"
    
    # Precise query using BAN fields
    params = {
        "qs": 'code_postal_brut:59000 AND numero_voie_ban:"43"',
        "q": "Brule Maison", # Street keywords in q for fuzzy matching
        "size": 10
    }
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, params=params, timeout=30)
            data = r.json()
            results = data.get("results", [])
            print(f"Total: {data.get('total')}, Found: {len(results)}")
            for res in results:
                print(f"- {res.get('adresse_brut')} (DPE: {res.get('numero_dpe')})")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_hyper_precision())
