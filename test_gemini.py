import httpx
import asyncio
import os

# Get key from environment OR hardcoded fallback from ai_service
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBd7LfTgrf4OM6Z-6ygI0uDRiflmjJozxo")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_KEY}"

async def test_gemini():
    print(f"Testing Gemini API with key: {GEMINI_KEY[:10]}...")
    
    payload = {
        "contents": [
            {
                "parts": [{"text": "Dis 'SPREA est pret' en français pour confirmer la connexion."}]
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(GEMINI_URL, json=payload, timeout=30.0)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                res_json = response.json()
                print("Raw Response:", res_json)
                if 'candidates' in res_json:
                    text = res_json['candidates'][0]['content']['parts'][0]['text']
                    print(f"Success! Response: {text}")
                else:
                    print("Unexpected response structure.")
            else:
                print(f"Error: {response.text}")
                
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
