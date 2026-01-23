import httpx
import asyncio
import json

async def find_specific():
    dataset_id = "meg-83tjwtg8dyz4vv7h1dqe"
    base_url = f"https://data.ademe.fr/data-fair/api/v1/datasets/{dataset_id}/lines"
    
    # Test 1: Direct search for Brulé Maison
    print("Test: Search for 'Brule Maison' in Lille")
    params = {
        "q": "Brule Maison",
        "qs": 'code_postal_brut:"59000"',
        "size": 100
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(base_url, params=params, timeout=30)
        data = r.json()
        results = data.get("results", [])
        print(f"Total results: {data.get('total')}, Found in page: {len(results)}")
        for res in results:
            addr = res.get("adresse_brut", "")
            if "43" in addr:
                print(f"MATCH FOUND: {addr} (DPE: {res.get('numero_dpe')})")

if __name__ == "__main__":
    asyncio.run(find_specific())
