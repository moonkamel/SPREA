# Vercel Trigger: Renamed entrypoint to main.py
import os
import io
import logging
import json
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException
import pdfplumber
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    from api.ademe_client import AdemeConnector
except ImportError:
    from ademe_client import AdemeConnector

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

# Initialize Connector
ademe = AdemeConnector()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SPREA DPE PDF Parser")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "online", "message": "SPREA API is running. Use /docs for API documentation."}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# --- Core Logic ---

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts text using pdfplumber with OCR fallback."""
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
        return {"error": "LLM analysis failed", "details": str(e)}

# --- Endpoints ---

@app.get("/search-address")
async def search_address(q: str):
    """Search for a property by address using BAN + ADEME."""
    try:
        results = await ademe.search_by_address(q)
        return {"count": len(results), "results": results}
    except Exception as e:
        logger.error(f"Address search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search-dpe/{dpe_number}")
async def search_dpe(dpe_number: str):
    """Search for a property by DPE number."""
    try:
        results = await ademe.search_by_dpe_number(dpe_number)
        return {"count": len(results), "results": results}
    except Exception as e:
        logger.error(f"DPE search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from pydantic import BaseModel
from fastapi.responses import Response
try:
    from api.pdf_service import pdf_service
except ImportError:
    from pdf_service import pdf_service

class ReportRequest(BaseModel):
    address: str
    surface: float
    year: Any
    ademe_dpe_number: Optional[str] = "N/A"
    current_label: str
    new_label: str
    initial_cep: float
    new_cep: float
    ges_value: float
    new_ges: float
    total_cost: float
    subsidies: float
    rest_to_pay: float
    latent_gain: float
    annual_savings: float
    roi_years: int
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

@app.post("/generate-report")
async def generate_report(data: ReportRequest):
    """Generates a PDF report from simulation results."""
    try:
        pdf_bytes = pdf_service.generate(data.dict())
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Rapport_SPREA_{data.address.replace(' ', '_')}.pdf"}
        )
    except Exception as e:
        logger.error(f"PDF Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-dpe")
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

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
