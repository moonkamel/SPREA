import httpx
import asyncio

async def test_ademe():
    base_url = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe-logements-existants-depuis-juillet-2021/lines"
    
    # Test 1: Search by postcode only
    print("Test 1: Postcode only (59000)")
    async with httpx.AsyncClient() as client:
        params = {"q": "59000", "size": 5}
        r = await client.get(base_url, params=params)
        print(f"Status: {r.status_code}, Results: {len(r.json().get('results', []))}")

    # Test 2: Search by street keywords
    print("\nTest 2: Street keywords ('Brule Maison 59000')")
    async with httpx.AsyncClient() as client:
        params = {"q": "Brule Maison 59000", "size": 10}
        r = await client.get(base_url, params=params)
        results = r.json().get('results', [])
        print(f"Status: {r.status_code}, Results: {len(results)}")
        for i, res in enumerate(results):
            print(f"[{i}] {res.get('adresse_brut')}")

    # Test 3: Search by number and street
    print("\nTest 3: Number and street ('43 Rue Brule Maison')")
    async with httpx.AsyncClient() as client:
        params = {"q": "43 Rue Brule Maison Lille", "size": 5}
        r = await client.get(base_url, params=params)
        results = r.json().get('results', [])
        print(f"Status: {r.status_code}, Results: {len(results)}")
        for res in results:
            print(f"- {res.get('adresse_brut')} (DPE: {res.get('numero_dpe')})")

if __name__ == "__main__":
    asyncio.run(test_ademe())
