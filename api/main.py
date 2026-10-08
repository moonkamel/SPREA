import os
import io
import logging
import json
import re
import time
import unicodedata
from datetime import date
from collections import defaultdict, deque
from dotenv import load_dotenv

load_dotenv()
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, APIRouter, Response, Request, Depends
from pydantic import BaseModel
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    from api.ademe_client import AdemeConnector, PropertySchema
    from api.engine import DPECalculator
    from api.simulation import WORKS_CATALOG, SimulationInput, suggest_works, simulate as run_simulation
except ImportError:
    from ademe_client import AdemeConnector, PropertySchema
    from engine import DPECalculator
    from simulation import WORKS_CATALOG, SimulationInput, suggest_works, simulate as run_simulation

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
engine = DPECalculator()
try:
    from api.ai_service import ai_service
except ImportError:
    from ai_service import ai_service

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

# --- Rate limiting ---
# In-memory sliding window per client IP. Protects the paid endpoints (LLM calls)
# from abuse. On serverless platforms memory is per instance, so this is a
# best-effort guard, not a hard quota.

class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls: Dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request):
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        window = self.calls[ip]
        while window and now - window[0] > self.period:
            window.popleft()
        if len(window) >= self.max_calls:
            raise HTTPException(status_code=429, detail="Trop de requêtes, veuillez réessayer plus tard.")
        window.append(now)

search_limiter = RateLimiter(max_calls=int(os.getenv("RATE_LIMIT_SEARCH_PER_MIN", "30")), period_seconds=60)
# The UI re-simulates on every change (debounced), so this one is looser
simulate_limiter = RateLimiter(max_calls=int(os.getenv("RATE_LIMIT_SIMULATE_PER_MIN", "120")), period_seconds=60)
ai_limiter = RateLimiter(max_calls=int(os.getenv("RATE_LIMIT_AI_PER_HOUR", "10")), period_seconds=3600)

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

def enrich_property(prop: PropertySchema) -> Dict[str, Any]:
    """API representation of a property, with losses and suggested works."""
    d = prop.model_dump(mode="json")
    calc = engine.calculate(prop)
    recos = engine.get_recommendations(prop)
    suggestions = suggest_works(
        prop.building_type,
        prop.dpe_class_current.value if prop.dpe_class_current else None,
        prop.consumption_level,
        [r["id"] for r in recos],
        calc["loss_breakdown"],
        prop.systems[0].energy_source if prop.systems else None,
    )
    d["recommended_works"] = recos
    d["loss_breakdown"] = calc["loss_breakdown"]
    d["suggested_works"] = suggestions["suggested"]
    d["preselected_works"] = suggestions["preselected"]
    return d

@router.get("/search-address", dependencies=[Depends(search_limiter)])
async def search_address(q: str):
    """Search for a property by address using BAN + ADEME."""
    try:
        logger.info(f"Searching address: {q}")
        results = await ademe.search_by_address(q)

        api_results = []
        for r in results:
            try:
                api_results.append(enrich_property(r))
            except Exception as item_err:
                logger.error(f"Error mapping item {r.address}: {item_err}")
                continue

        return {"count": len(api_results), "results": api_results}
    except Exception as e:
        logger.error(f"Address search crash: {e}", exc_info=True)
        return {"count": 0, "results": [], "error": "La recherche a échoué."}

@router.get("/search-dpe/{dpe_number}", dependencies=[Depends(search_limiter)])
async def search_dpe(dpe_number: str):
    """Search for a property by DPE number."""
    try:
        logger.info(f"Searching DPE: {dpe_number}")
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

@router.get("/works")
async def works_catalog():
    """Catalog of retrofit works the simulation knows about."""
    return {"works": [
        {"id": w["id"], "name": w["name"], "description": w["description"], "impact_kwh": w["impact_kwh"]}
        for w in WORKS_CATALOG
    ]}

@router.post("/simulate", dependencies=[Depends(simulate_limiter)])
async def simulate(data: SimulationInput):
    """Run the technical-economic simulation for a set of works."""
    try:
        return run_simulation(data)
    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="La simulation a échoué.")

try:
    from api.pdf_service import pdf_service
except ImportError:
    from pdf_service import pdf_service

class ReportRequest(BaseModel):
    address: str
    surface: float
    year: Any = "N/A"
    construction_period: Optional[str] = "N/A"
    building_type: Optional[str] = "Logement"
    ademe_dpe_number: Optional[str] = "N/A"
    current_label: str = "G"
    new_label: str = "G"
    initial_cep: float = 0.0
    new_cep: float = 0.0
    ges_value: float = 0.0
    new_ges: float = 0.0
    total_cost: float = 0.0
    subsidies: float = 0.0
    rest_to_pay: float = 0.0
    latent_gain: float = 0.0
    annual_savings: float = 0.0
    roi_years: Optional[int] = None
    detailed_costs: Optional[list] = []
    yield_brut: Optional[float] = 0.0
    cashflow: Optional[float] = 0.0
    purchase_price: Optional[float] = 0.0
    ban_date: Optional[str] = None
    cee_est: Optional[float] = 0.0
    eco_ptz_amount: Optional[float] = 0.0
    pam_amount: Optional[float] = 0.0
    tax_benefit: Optional[float] = 0.0
    has_iti: Optional[bool] = False
    user_profile: Optional[str] = "propriétaire"
    focus_mpr: Optional[str] = None
    focus_cee: Optional[str] = None
    focus_eco_ptz: Optional[str] = None
    # When given, every figure of the report is recomputed server side
    simulation: Optional[SimulationInput] = None

def safe_filename(text: str) -> str:
    """ASCII-only filename, safe to put in a Content-Disposition header."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_")[:80] or "bien"

@router.post("/generate-report", dependencies=[Depends(ai_limiter)])
async def generate_report(data: ReportRequest):
    """Generates a PDF report from simulation results with AI narrative."""
    try:
        report_data = data.model_dump(exclude={"simulation"})
        if data.simulation:
            sim = run_simulation(data.simulation)
            prop = data.simulation.property
            report_data.update({
                "surface": prop.surface,
                "current_label": sim["current_label"],
                "new_label": sim["new_label"],
                "initial_cep": sim["initial_cep"],
                "new_cep": sim["new_cep"],
                "ges_value": sim["initial_ges"],
                "new_ges": sim["new_ges"],
                "total_cost": sim["cost"],
                "subsidies": sim["subsidies"],
                "cee_est": sim["cee_est"],
                "rest_to_pay": sim["rest_to_pay"],
                "latent_gain": sim["latent_gain"],
                "annual_savings": sim["annual_savings"],
                "roi_years": round(sim["roi_years"]) if sim["roi_years"] is not None else None,
                "detailed_costs": sim["detailed_costs"],
                "yield_brut": sim["yield_brut"],
                "cashflow": sim["cashflow"],
                "purchase_price": data.simulation.purchase_price,
                "ban_date": date.fromisoformat(sim["ban_date"]).strftime("%d/%m/%Y") if sim["ban_date"] else None,
                "eco_ptz_amount": sim["eco_ptz_amount"],
                "tax_benefit": sim["tax_benefit"],
                "has_iti": sim["has_iti"],
                "user_profile": "investisseur" if data.simulation.is_investor else "propriétaire",
            })
        
        # 1. Generate AI Narrative
        logger.info(f"Generating AI narrative for profile: {report_data['user_profile']}")
        narrative = await ai_service.generate_narrative(report_data, report_data["user_profile"])
        report_data["ai_narrative"] = narrative
        
        # 2. Generate PDF
        pdf_bytes = pdf_service.generate(report_data)
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Rapport_SPREA_{safe_filename(data.address)}.pdf"}
        )
    except Exception as e:
        logger.error(f"PDF Generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="La génération du rapport a échoué.")

@router.post("/analyze-dpe", dependencies=[Depends(ai_limiter)])
async def analyze_dpe(file: UploadFile = File(...)):
    # 1. Validation
    logger.info(f"Received PDF upload request: {file.filename}")
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

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
