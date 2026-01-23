import httpx
import asyncio

async def inspect_schema():
    dataset_id = "meg-83tjwtg8dyz4vv7h1dqe"
    url = f"https://data.ademe.fr/data-fair/api/v1/datasets/{dataset_id}/schema"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        schema = r.json()
        print("Fields in dataset:")
        for field in schema:
            name = field.get("name")
            if name:
                if "ban" in name.lower() or "insee" in name.lower() or "adresse" in name.lower():
                    print(f"- {name}: {field.get('title')}")

if __name__ == "__main__":
    asyncio.run(inspect_schema())
