import httpx
import asyncio

async def test_ademe():
    base_url = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
    
    # Test 4: Precision search for user address
    print("\nTest 4: User problematic address ('brûle maison 59000')")
    async with httpx.AsyncClient() as client:
        params = {"q": "brûle maison 59000", "size": 100}
        r = await client.get(base_url, params=params)
        if r.status_code != 200:
            print(f"FAILED with {r.status_code}")
            return
            
        results = r.json().get('results', [])
        print(f"Status: {r.status_code}, Results: {len(results)}")
        matched = False
        for i, res in enumerate(results):
            addr = res.get('adresse_brut', '')
            if "43" in addr and "BR" in addr.upper():
                print(f"!!! FOUND MATCH at index {i}: {addr}")
                matched = True
        if not matched:
            print("No match found in top 100.")

    # Test 5: Search for the DPE number from screenshot
    # The screenshot number: 2359L0561/56J
    print("\nTest 5: Search by DPE number ('2359L0561/56J')")
    async with httpx.AsyncClient() as client:
        params = {"q": "2359L0561/56J", "q_fields": "numero_dpe"}
        r = await client.get(base_url, params=params)
        results = r.json().get('results', [])
        print(f"Status: {r.status_code}, Results: {len(results)}")
        if results:
             print(f"MATCH: {results[0].get('adresse_brut')}")

if __name__ == "__main__":
    asyncio.run(test_ademe())
