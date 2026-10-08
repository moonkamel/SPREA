# SPREA

Simulateur de rénovation énergétique : à partir du DPE d'un logement (données
ADEME), estime les travaux, la nouvelle étiquette, les aides (MaPrimeRénov',
CEE, Éco-PTZ), le reste à charge et les économies, et produit un rapport PDF.

## Structure

| Dossier | Contenu |
| --- | --- |
| `src/` | Interface React (Vite, Tailwind) |
| `api/main.py` | API FastAPI : recherche, simulation, analyse de PDF DPE |
| `api/simulation.py` | Moteur de simulation (seule source de calcul) |
| `api/envelope.py` | Modèle de déperditions du logement |
| `api/aids.py` | Barèmes MaPrimeRénov' / CEE |
| `api/accounts.py`, `auth.py`, `billing.py`, `store.py` | Comptes (Supabase) et paiement (Stripe) |
| `api/ademe_client.py` | Accès aux données DPE de l'ADEME |
| `api/pdf_service.py`, `ai_service.py` | Rapport PDF et texte rédigé par l'IA |
| `supabase/migrations/` | Schéma de la base |
| `scripts/` | Outils de développement |
| `tests/` | Tests (pytest) |
| `docs/` | Mise en service des comptes et du paiement |

## Développement

```
cp .env.example .env            # puis renseigner les clés
pip install -r requirements-dev.txt
npm install

uvicorn api.main:app --reload --port 8000
npm run dev                     # http://localhost:5173, /api est relayé vers le port 8000
```

## Vérifications

```
pytest
npm run build
```
