import httpx
import asyncio
import os

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBd7LfTgrf4OM6Z-6ygI0uDRiflmjJozxo")
MODELS_URL = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"

async def list_models():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(MODELS_URL)
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                for m in data.get('models', []):
                    name = m.get('name')
                    methods = m.get('supportedGenerationMethods', [])
                    print(f"- {name} | {methods}")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(list_models())
