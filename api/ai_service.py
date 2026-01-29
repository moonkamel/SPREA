import httpx
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCLlZZd0RNX7EYm49yOD2jeAhlXCT9O2aE")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}"

class AIService:
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.model_name = model_name

    async def generate_narrative(self, data: Dict[str, Any], user_profile: str = "propriétaire") -> str:
        """
        Generates a personalized narrative for the renovation report using direct REST API.
        """
        try:
            prompt_text = f"""
            Tu es un expert en rénovation énergétique pour SPREA (Intelligent Property). 
            Rédige une analyse synthétique et percutante (150-200 mots) pour un rapport de rénovation.
            
            DONNÉES DU BIEN :
            - Adresse : {data.get('address')}
            - État actuel : DPE {data.get('current_label')} ({data.get('initial_cep')} kWh/m².an)
            - État projeté : DPE {data.get('new_label')} ({data.get('new_cep')} kWh/m².an)
            - Reste à charge après aides : {data.get('rest_to_pay')} €
            - Gain de valeur immobilière estimé : {data.get('latent_gain')} €
            - Économies annuelles : {data.get('annual_savings')} €/an
            
            PROFIL UTILISATEUR : {user_profile}
            
            RÈGLES :
            1. Si le profil est 'investisseur', insiste sur la rentabilité, la Loi Climat (interdiction de louer) et la plus-value verte.
            2. Si le profil est 'propriétaire', insiste sur le confort thermique et la baisse drastique des factures.
            3. Utilise un ton professionnel, rassurant et expert.
            4. Ne mentionne pas de "Données fournies", écris comme si tu avais analysé le dossier.
            5. Structure en 2 courts paragraphes : "L'Analyse de l'Expert" et "La Stratégie Conseillée".
            """
            
            payload = {
                "contents": [
                    {
                        "parts": [{"text": prompt_text}]
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(GEMINI_URL, json=payload, timeout=30.0)
                response.raise_for_status()
                res_json = response.json()
                logger.info(f"Gemini Response: {res_json}")
                
                # Extract text from Gemini structure
                if 'candidates' in res_json and len(res_json['candidates']) > 0:
                    parts = res_json['candidates'][0].get('content', {}).get('parts', [])
                    if parts:
                        return parts[0].get('text', '')
                
                logger.error(f"Unexpected Gemini structure: {res_json}")
                return "L'IA n'a pas pu générer l'analyse. Veuillez vérifier les paramètres."
                
        except Exception as e:
            logger.error(f"Gemini REST Error: {e}")
            return "Une erreur est survenue lors de la génération de l'analyse personnalisée par l'IA. Veuillez consulter les chiffres techniques détaillés ci-dessous."

ai_service = AIService()
