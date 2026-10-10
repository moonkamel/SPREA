import os
import io
import logging
import json
from dotenv import load_dotenv

load_dotenv()
import re
from typing import Any, Dict, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, APIRouter, Response, Depends
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    from api.ademe_client import AdemeConnector, PropertySchema
    from api.dvf import market_price
    from api.simulation import (WORKS_CATALOG, SimulationInput, SimulationProperty, build_envelope,
                                suggest_works, simulate as run_simulation)
except ImportError:
    from ademe_client import AdemeConnector, PropertySchema
    from dvf import market_price
    from simulation import (WORKS_CATALOG, SimulationInput, SimulationProperty, build_envelope,
                            suggest_works, simulate as run_simulation)

# LLM Client setup (OpenAI style)
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        LLM_AVAILABLE = True
    except ImportError:
        LLM_AVAILABLE = False
        client = None
else:
    LLM_AVAILABLE = False
    client = None

# Initialize Connector & Engine
ademe = AdemeConnector()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SPREA DPE PDF Parser")

from fastapi.middleware.cors import CORSMiddleware
# Frontend and API are served from the same origin on Vercel, so CORS is only
# needed for extra origins explicitly listed in ALLOWED_ORIGINS (comma separated).
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global Error on {request.url}: {exc}", exc_info=True)
    return Response(
        content=json.dumps({"detail": "Erreur interne du serveur.", "path": request.url.path}),
        status_code=500,
        media_type="application/json"
    )

try:
    from api.ratelimit import search_limiter, simulate_limiter, ai_limiter
    from api.auth import current_user
    from api.accounts import router as accounts_router, subscriber_access
    from api.contacts import router as contacts_router
    from api.alerts import router as alerts_router
    from api.valuation import router as valuation_router
    from api.observatoire import router as observatoire_router
    from api.quotes import router as quotes_router
    from api.teams import router as teams_router
    from api.rge import router as rge_router
    from api.immeuble import router as immeuble_router
    from api.monopro import router as monopro_router
    from api.copro_docs import router as copro_docs_router
except ImportError:
    from ratelimit import search_limiter, simulate_limiter, ai_limiter
    from auth import current_user
    from accounts import router as accounts_router, subscriber_access
    from contacts import router as contacts_router
    from alerts import router as alerts_router
    from valuation import router as valuation_router
    from observatoire import router as observatoire_router
    from quotes import router as quotes_router
    from teams import router as teams_router
    from rge import router as rge_router
    from immeuble import router as immeuble_router
    from monopro import router as monopro_router
    from copro_docs import router as copro_docs_router

@app.get("/")
async def root():
    return {"status": "online", "message": "SPREA API is running. Use /docs for API documentation."}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# --- Core Logic ---

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts text using pdfplumber with OCR fallback."""
    import pdfplumber
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                elif OCR_AVAILABLE:
                    # Fallback to OCR if page has no selectable text
                    logger.info("No text found on page, attempting OCR fallback.")
                    img = page.to_image(resolution=300).original
                    text += pytesseract.image_to_string(img) + "\n"
    except Exception as e:
        logger.error(f"Error during text extraction: {e}")
        raise HTTPException(status_code=500, detail="Could not extract text from PDF.")
    
    return text.strip()

def analyze_text_with_llm(raw_text: str) -> Dict[str, Any]:
    """Sends raw text to LLM for structured extraction."""
    if not LLM_AVAILABLE:
        logger.warning("OpenAI client not installed. Returning empty structure.")
        return {}

    prompt = f"""
    You are a French Energetic Performance (DPE) expert. 
    Analyze the following raw text extracted from a French DPE 2021 PDF.
    Extract the following data in a strict JSON format. 
    If a value is missing or unreadable, return null.

    RULES:
    - numero_dpe: 13 characters.
    - date_visite: YYYY-MM-DD.
    - etiquette_actuelle: A, B, C, D, E, F, or G.
    - consommation_primaire: integer in kWh/m2/an.
    - surface_habitable: float.
    - isolation: u-values in W/m2.K.

    TEXT:
    {raw_text[:8000]}  # Limit text to avoid token overflow for simple demo

    JSON STRUCTURE:
    {{
      "numero_dpe": "string",
      "date_visite": "YYYY-MM-DD",
      "etiquette_actuelle": "char",
      "consommation_primaire": "int",
      "surface_habitable": "float",
      "altitude": "int",
      "chauffage": {{
        "type_generateur": "string",
        "annee_installation": "int"
      }},
      "isolation": {{
        "mur_u_value": "float",
        "toiture_u_value": "float",
        "vitrage_type": "string"
      }}
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-2024-08-06", # Using a highly capable model for table parsing
            messages=[
                {"role": "system", "content": "You are a specialized data extractor."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error during LLM analysis: {e}")
        return {"error": "LLM analysis failed"}

router = APIRouter(prefix="/api")

@router.get("/")
async def api_root():
    return {"status": "online", "message": "SPREA API is running."}

def simulation_property(prop: PropertySchema) -> SimulationProperty:
    return SimulationProperty(
        surface=prop.shab or 50,
        initial_cep=prop.consumption_level or 350,
        ges_value=prop.ges_value,
        official_label=prop.dpe_class_current.value if prop.dpe_class_current else None,
        dpe_date=str(prop.date_etablissement)[:10] if prop.date_etablissement else None,
        building_type=prop.building_type,
        postcode=prop.postcode,
        construction_year=prop.construction_year,
        construction_period=prop.construction_period,
        heating_energy=prop.systems[0].energy_source if prop.systems else None,
        final_consumption=prop.final_consumption,
        insulation_quality=prop.insulation_quality,
        dpe_losses=prop.dpe_losses,
        heating_generator=(prop.details or {}).get("heating_system"),
        heating_installation=(prop.details or {}).get("heating_installation"),
        hot_water_system=(prop.details or {}).get("hot_water_system"),
        hot_water_installation=(prop.details or {}).get("hot_water_installation"),
        ventilation=(prop.details or {}).get("ventilation"),
    )

def enrich_property(prop: PropertySchema) -> Dict[str, Any]:
    """API representation of a property, with heat losses and suggested works."""
    d = prop.model_dump(mode="json")
    sim_prop = simulation_property(prop)
    suggestions = suggest_works(sim_prop, prop.dpe_class_current.value if prop.dpe_class_current else None)
    d["loss_shares"] = build_envelope(sim_prop).shares()
    d["suggested_works"] = suggestions["suggested"]
    d["preselected_works"] = suggestions["preselected"]
    return d

@router.get("/search-address", dependencies=[Depends(search_limiter), Depends(subscriber_access)])
async def search_address(q: str):
    """Search for a property by address using BAN + ADEME."""
    try:
        logger.info("Searching by address")
        results = await ademe.search_by_address(q)

        api_results = []
        for r in results:
            try:
                api_results.append(enrich_property(r))
            except Exception as item_err:
                logger.error(f"Error mapping item: {item_err}")
                continue

        return {"count": len(api_results), "results": api_results}
    except Exception as e:
        logger.error(f"Address search crash: {e}", exc_info=True)
        return {"count": 0, "results": [], "error": "La recherche a échoué."}

@router.get("/search-dpe/{dpe_number}", dependencies=[Depends(search_limiter), Depends(subscriber_access)])
async def search_dpe(dpe_number: str):
    """Search for a property by DPE number."""
    try:
        logger.info("Searching by DPE number")
        prop = await ademe.search_by_dpe_number(dpe_number)
        if prop:
            try:
                return {"count": 1, "results": [enrich_property(prop)]}
            except Exception as map_err:
                logger.error(f"DPE Mapping Error: {map_err}")
                return {"count": 1, "results": [prop.model_dump(mode="json")]}
        return {"count": 0, "results": []}
    except Exception as e:
        logger.error(f"DPE search failed: {e}", exc_info=True)
        return {"count": 0, "results": [], "error": "La recherche a échoué."}

@router.get("/market-price", dependencies=[Depends(search_limiter), Depends(subscriber_access)])
async def get_market_price(insee: str, building_type: str = "", lat: Optional[float] = None, lon: Optional[float] = None,
                           surface: Optional[float] = None):
    """Local price per m2 of comparable DVF sales, for the green value. None when unknown."""
    if not re.fullmatch(r"[0-9][0-9AB][0-9]{3}", insee.upper()):
        raise HTTPException(status_code=400, detail="Code commune invalide.")
    if surface is not None and not 5 <= surface <= 10000:
        surface = None
    result = await market_price(insee, building_type, lat, lon, surface)
    return result or {"price_per_m2": None}

@router.get("/works")
async def works_catalog():
    """Catalog of retrofit works the simulation knows about."""
    return {"works": [
        {"id": w["id"], "name": w["name"], "description": w["description"]}
        for w in WORKS_CATALOG
    ]}

@router.post("/simulate", dependencies=[Depends(simulate_limiter), Depends(subscriber_access)])
async def simulate(data: SimulationInput):
    """Run the technical-economic simulation for a set of works."""
    try:
        return run_simulation(data)
    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="La simulation a échoué.")

@router.post("/analyze-dpe", dependencies=[Depends(ai_limiter), Depends(subscriber_access)])
async def analyze_dpe(file: UploadFile = File(...)):
    # 1. Validation
    logger.info("Received DPE PDF upload")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDFs are allowed.")
    
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

    # 2. Text Extraction
    try:
        raw_text = extract_text_from_pdf(file_bytes)
        logger.info(f"Extracted {len(raw_text)} chars from PDF.")
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Could not extract text from PDF.")

    if not raw_text:
        raise HTTPException(status_code=422, detail="PDF seems empty or unreadable.")

    # 3. LLM Analysis
    extracted_data = analyze_text_with_llm(raw_text)
    logger.info("LLM extraction complete.")

    return {
        "filename": file.filename,
        "raw_text_length": len(raw_text),
        "data": extracted_data
    }

app.include_router(router)
app.include_router(accounts_router)
app.include_router(contacts_router)
app.include_router(alerts_router)
app.include_router(valuation_router)
app.include_router(observatoire_router)
app.include_router(quotes_router)
app.include_router(teams_router)
app.include_router(rge_router)
app.include_router(immeuble_router)
app.include_router(monopro_router)
app.include_router(copro_docs_router)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
