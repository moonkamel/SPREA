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
    address: str
    ademe_dpe_number: Optional[str] = Field(None, max_length=13)
    construction_year: Optional[int] = None
    shab: float
    altitude: Optional[float] = None
    climate_zone: Optional[ClimateZone] = None
    dpe_class_current: Optional[DPEClass] = None
    ges_class_current: Optional[DPEClass] = None
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

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5)
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
                postcode = feature["properties"]["postcode"]
                street = feature["properties"]["street"] or feature["properties"]["name"]
                # Clean street name: "Rue Brûle-Maison" -> "Brûle Maison"
                street_clean = street.lower().replace("rue ", "").replace("boulevard ", "").replace("avenue ", "").replace("-", " ")
                coords = feature["geometry"]["coordinates"] # [lon, lat]

                # 2. Search ADEME with precision keywords (Pivot Strategy)
                # Query: Street name in 'q', Postcode in 'qs' (filter)
                ademe_params = {
                    "q": street_clean,
                    "qs": f'code_postal_brut:"{postcode}"',
                    "size": 100
                }
                logger.info(f"Querying ADEME with: {ademe_params}")
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
            construction_year=construction_year,
            shab=float(raw.get("surface_habitable_logement", 0.0)),
            altitude=raw.get("classe_altitude"),
            climate_zone=self._map_climate_zone(raw.get("zone_climatique")),
            dpe_class_current=raw.get("etiquette_dpe"),
            ges_class_current=raw.get("etiquette_ges"),
            date_etablissement=raw.get("date_etablissement_dpe"),
            building_type=raw.get("type_batiment"),
            is_estimated=is_estimated
        )

        # Geopoint handling if present ([lat, lon])
        geopoint = raw.get("_geopoint")
        if geopoint and len(geopoint) == 2:
            prop.latitude = geopoint[0]
            prop.longitude = geopoint[1]

        # Mapping Walls
        # If surface_murs is missing, we use a ratio of SHAB as estimate
        surface_murs = raw.get("surface_murs_exterieurs")
        if not surface_murs:
            shab = prop.shab
            # Simple ratio estimate for walls: House ~ 1.5*SHAB, Apt ~ 0.8*SHAB
            type_bat = raw.get("type_batiment", "").lower()
            ratio = 1.5 if "maison" in type_bat else 0.8
            surface_murs = shab * ratio
            is_estimated = True

        prop.walls.append(WallSchema(
            surface=float(surface_murs),
            u_value=u_wall,
            material=raw.get("type_materiau_mur_exterieur"),
            is_estimated=is_estimated
        ))

        # Mapping Windows
        surface_baies = raw.get("surface_baies_vitrees")
        if surface_baies:
            prop.windows.append(WindowSchema(
                surface=float(surface_baies),
                u_value=raw.get("u_baies_vitrees"),
                glazing_type=raw.get("type_vitrage"),
                is_estimated=(raw.get("u_baies_vitrees") is None)
            ))

        # Mapping Systems
        energy_source = raw.get("type_energie_principale_chauffage") or raw.get("type_generateur_chauffage_principal")
        if energy_source:
            prop.systems.append(SystemSchema(
                system_type="chauffage",
                energy_source=energy_source,
                efficiency_etas=raw.get("ubat_w_par_m2_k") # Using Ubat as proxy if others missing
            ))

        return prop

    def _map_climate_zone(self, zone: Optional[str]) -> Optional[ClimateZone]:
        if not zone: return None
        # Normalize: H1 instead of H1a if necessary, or direct match
        try:
            return ClimateZone(zone)
        except ValueError:
            # Handle possible differences in documentation vs actual values
            if zone in ["H1", "H2", "H3"]:
                matches = [z for z in ClimateZone if z.startswith(zone)]
                return matches[0] if matches else None
            return None

# Example Usage (Commented out)
# async def main():
#     connector = AdemeConnector()
#     prop = await connector.search_by_dpe_number("2134E1234567A")
#     print(prop)

# if __name__ == "__main__":
#     asyncio.run(main())
