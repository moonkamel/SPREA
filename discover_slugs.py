import httpx
import asyncio

async def discover_slugs():
    url = "https://data.ademe.fr/data-fair/api/v1/datasets"
    params = {"q": "dpe logements existants", "size": 10}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        data = r.json()
        for ds in data.get("results", []):
            print(f"ID: {ds['id']} | Title: {ds['title']}")

if __name__ == "__main__":
    asyncio.run(discover_slugs())
