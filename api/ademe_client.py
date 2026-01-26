import logging
import asyncio
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator
import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Internal Enums matching Database ---

class ClimateZone(str, Enum):
    H1a = "H1a"
    H1b = "H1b"
    H1c = "H1c"
    H2a = "H2a"
    H2b = "H2b"
    H2c = "H2c"
    H2d = "H2d"
    H3 = "H3"

class DPEClass(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"

class Orientation(str, Enum):
    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"

# --- Internal Pydantic Schemas ---

class WallSchema(BaseModel):
    surface: float
    u_value: Optional[float] = None
    resistance: Optional[float] = None
    orientation: Optional[Orientation] = None
    insulation_type: Optional[str] = None
    material: Optional[str] = None
    is_estimated: bool = False

class WindowSchema(BaseModel):
    surface: float
    u_value: Optional[float] = None
    glazing_type: Optional[str] = None
    solar_factor_sw: Optional[float] = None
    has_shutters: bool = False
    is_estimated: bool = False

class SystemSchema(BaseModel):
    system_type: str
    energy_source: Optional[str] = None
    efficiency_etas: Optional[float] = None
    generation_year: Optional[int] = None
    is_estimated: bool = False

class PropertySchema(BaseModel):
    address: str = "Adresse Inconnue"
    ademe_dpe_number: Optional[str] = None
    construction_year: Optional[int] = None
    construction_period: Optional[str] = None
    shab: float = 0.0
    altitude: Optional[float] = None
    climate_zone: Optional[ClimateZone] = None
    dpe_class_current: Optional[DPEClass] = None
    ges_class_current: Optional[DPEClass] = None
    consumption_level: Optional[float] = None
    ges_value: Optional[float] = None
    date_etablissement: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    building_type: Optional[str] = None # Maison, Appartement, etc.
    walls: List[WallSchema] = []
    windows: List[WindowSchema] = []
    systems: List[SystemSchema] = []
    is_estimated: bool = False

# --- ADEME Connector ---

class AdemeConnector:
    BASE_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
    BAN_URL = "https://api-adresse.data.gouv.fr/search/"

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=stop_after_attempt(2)
    )
    async def _make_request(self, client: httpx.AsyncClient, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response = await client.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    async def search_by_dpe_number(self, dpe_number: str) -> Optional[PropertySchema]:
        """Fetch technical details of a specific DPE."""
        async with httpx.AsyncClient() as client:
            try:
                params = {"q": dpe_number, "q_fields": "numero_dpe"}
                data = await self._make_request(client, self.BASE_URL, params)
                
                if not data.get("results"):
                    logger.warning(f"No DPE found for number: {dpe_number}")
                    return None
                
                raw_data = data["results"][0]
                return self._map_to_internal(raw_data)
            except Exception as e:
                logger.error(f"ADEME API Error: {e}")
                return None

    async def search_by_address(self, address: str) -> List[PropertySchema]:
        """Geocode via BAN then search on ADEME."""
        async with httpx.AsyncClient() as client:
            try:
                # 1. Geocoding via BAN
                ban_params = {"q": address, "limit": 1}
                ban_data = await self._make_request(client, self.BAN_URL, ban_params)
                
                if not ban_data.get("features"):
                    logger.warning(f"Address not found via BAN: {address}")
                    return []
                
                feature = ban_data["features"][0]
                props = feature["properties"]
                postcode = props.get("postcode")
                housenumber = props.get("housenumber", "")
                street = props.get("street") or props.get("name")
                city = props.get("city", "")
                
                # Unaccent and clean for better matching
                def clean_text(text: str) -> str:
                    import unicodedata
                    if not text: return ""
                    return "".join(
                        c for c in unicodedata.normalize('NFD', text)
                        if unicodedata.category(c) != 'Mn'
                    ).lower().replace("-", " ")

                street_clean = clean_text(street)
                coords = feature["geometry"]["coordinates"] # [lon, lat]

                # 2. Search ADEME with Hyper-Precision (Pivot Strategy)
                # We use specific normalized fields from BAN already present in the ADEME dataset
                # This is much faster and more accurate than generic full-text search
                filters = []
                if postcode:
                    filters.append(f"code_postal_brut:{postcode}")
                if housenumber:
                    filters.append(f'numero_voie_ban:"{housenumber}"')
                if street:
                    # Stricter street match in qs
                    filters.append(f'adresse_brut:"*{street_clean}*"')
                
                ademe_params = {
                    "q": street_clean,
                    "qs": " AND ".join(filters) if filters else "",
                    "size": 100
                }
                
                logger.info(f"Querying ADEME with Hyper-Precision: {ademe_params}")
                ademe_data = await self._make_request(client, self.BASE_URL, ademe_params)
                
                results = []
                for raw_item in ademe_data.get("results", []):
                    mapped = self._map_to_internal(raw_item)
                    # We might not have exact coords from ADEME, so we use BAN's
                    if not mapped.latitude:
                        mapped.latitude = coords[1]
                        mapped.longitude = coords[0]
                    results.append(mapped)
                
                # Sort by date (most recent first)
                results.sort(key=lambda x: x.date_etablissement or "", reverse=True)
                return results
            except Exception as e:
                logger.error(f"Address search error: {e}")
                return []

    def _safe_float(self, val: Any, default: float = 0.0) -> float:
        if val is None: return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def _safe_int(self, val: Any, default: Optional[int] = None) -> Optional[int]:
        if val is None: return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def _map_to_internal(self, raw: Dict[str, Any]) -> PropertySchema:
        """Map flat ADEME JSON to structured PropertySchema with fallback logic."""
        
        construction_year = raw.get("annee_construction")
        is_estimated = False

        # Fallback for U values if missing (using discovered field names)
        # Note: If u_murs is not in documented select, we rely on fallbacks
        def get_fallback_u_wall(year: Optional[int]) -> float:
            if not year: return 1.5
            if year < 1974: return 2.5
            if 1975 <= year <= 1982: return 1.0
            if 1983 <= year <= 1988: return 0.8
            if 1989 <= year <= 2000: return 0.5
            return 0.3

        # We check for deperditions or assumed technical fields
        u_wall = raw.get("u_murs_exterieurs") # Might be available even if not in select enum
        if u_wall is None:
            u_wall = get_fallback_u_wall(construction_year)
            is_estimated = True

        # Mapping main property using official OpenAPI names
        prop = PropertySchema(
            address=raw.get("adresse_brut", raw.get("adresse_complete_brut", "Unknown")),
            ademe_dpe_number=raw.get("numero_dpe"),
            construction_year=self._safe_int(raw.get("annee_construction")),
            construction_period=raw.get("periode_construction") or raw.get("nom_periode_construction") or raw.get("periode_construction_ban"),
            shab=self._safe_float(raw.get("surface_habitable_logement"), 50.0), # Safer default
            altitude=self._safe_float(raw.get("classe_altitude")),
            climate_zone=self._map_climate_zone(raw.get("zone_climatique")),
            dpe_class_current=self._map_dpe_label(raw.get("etiquette_dpe")),
            ges_class_current=self._map_dpe_label(raw.get("etiquette_ges")),
            consumption_level=self._safe_float(raw.get("conso_5_usages_par_m2_ep", raw.get("consommation_energie_primaire_logement"))),
            ges_value=self._safe_float(raw.get("emission_ges_5_usages_par_m2")),
            date_etablissement=raw.get("date_etablissement_dpe"),
            building_type=raw.get("type_batiment", "Logement"),
            is_estimated=is_estimated
        )

        # Geopoint handling if present ([lat, lon])
        geopoint = raw.get("_geopoint")
        if geopoint and isinstance(geopoint, list) and len(geopoint) == 2:
            prop.latitude = self._safe_float(geopoint[0])
            prop.longitude = self._safe_float(geopoint[1])

        # Mapping Walls
        surface_murs = raw.get("surface_murs_exterieurs")
        if not surface_murs:
            shab = prop.shab
            type_bat = (raw.get("type_batiment") or "").lower()
            ratio = 1.5 if "maison" in type_bat else 0.8
            surface_murs = shab * ratio
            is_estimated = True

        prop.walls.append(WallSchema(
            surface=self._safe_float(surface_murs),
            u_value=u_wall,
            material=raw.get("type_materiau_mur_exterieur"),
            is_estimated=is_estimated
        ))

        # Mapping Windows
        surface_baies = raw.get("surface_baies_vitrees")
        if surface_baies:
            prop.windows.append(WindowSchema(
                surface=self._safe_float(surface_baies),
                u_value=self._safe_float(raw.get("u_baies_vitrees")),
                glazing_type=raw.get("type_vitrage"),
                is_estimated=(raw.get("u_baies_vitrees") is None)
            ))

        # Mapping Systems
        energy_source = raw.get("type_energie_principale_chauffage") or raw.get("type_generateur_chauffage_principal")
        if energy_source:
            prop.systems.append(SystemSchema(
                system_type="chauffage",
                energy_source=str(energy_source),
                efficiency_etas=self._safe_float(raw.get("ubat_w_par_m2_k"))
            ))

        return prop

    def _map_climate_zone(self, zone: Optional[str]) -> Optional[ClimateZone]:
        if not zone: return None
        try:
            return ClimateZone(zone)
        except ValueError:
            if zone in ["H1", "H2", "H3"]:
                matches = [z for z in ClimateZone if z.startswith(zone)]
                return matches[0] if matches else None
            return None

    def _map_dpe_label(self, label: Optional[str]) -> Optional[DPEClass]:
        if not label: return None
        label = str(label).upper().strip()
        try:
            return DPEClass(label)
        except ValueError:
            # Handle exotic labels or "A+" etc.
            if label.startswith("A"): return DPEClass.A
            if label.startswith("B"): return DPEClass.B
            if label.startswith("C"): return DPEClass.C
            if label.startswith("D"): return DPEClass.D
            if label.startswith("E"): return DPEClass.E
            if label.startswith("F"): return DPEClass.F
            if label.startswith("G"): return DPEClass.G
            return None

# Example Usage (Commented out)
# async def main():
#     connector = AdemeConnector()
#     prop = await connector.search_by_dpe_number("2134E1234567A")
#     print(prop)

# if __name__ == "__main__":
#     asyncio.run(main())
