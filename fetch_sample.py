import httpx
import asyncio
import json

async def fetch_sample():
    dataset_id = "meg-83tjwtg8dyz4vv7h1dqe"
    url = f"https://data.ademe.fr/data-fair/api/v1/datasets/{dataset_id}/lines"
    params = {"size": 1}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        data = r.json()
        if data.get("results"):
            print(json.dumps(data["results"][0], indent=2))
        else:
            print("No results found.")

if __name__ == "__main__":
    asyncio.run(fetch_sample())
