"""Building envelope model: where the heat goes, and how much each insulation
work reduces it, for a given dwelling.

Heat losses (W/K) are estimated per element from a typical geometry (surface,
house or apartment) and typical U values for the construction period, refined
by the insulation quality reported in the DPE when available. When the DPE
provides its own loss breakdown, it is used as the weighting instead.

Only ratios are used downstream (losses after / losses before), so the
simulation stays anchored on the official DPE consumption.
"""
import math
import re
from typing import Dict, Iterable, List, Optional

ELEMENTS = ["walls", "roof", "floor", "windows", "air", "bridges"]

# Construction periods (upper bound year) used by the reference tables
PERIOD_BOUNDS = [1947, 1974, 1988, 2000, 2012]  # index 5 = after 2012

# Typical U values (W/m2.K) per period: <1948, 1948-74, 1975-88, 1989-2000, 2001-12, >2012
U_BY_PERIOD = {
    "walls": [2.0, 2.5, 1.0, 0.6, 0.4, 0.25],
    "roof": [2.5, 2.5, 0.6, 0.4, 0.25, 0.15],
    "floor": [2.0, 2.0, 1.0, 0.6, 0.4, 0.25],
    "windows": [4.5, 4.0, 2.9, 2.6, 1.8, 1.4],
}
# Air change rate (vol/h): ventilation + infiltrations
AIR_CHANGE_BY_PERIOD = [1.2, 1.2, 0.9, 0.7, 0.5, 0.4]

# U value implied by the DPE insulation quality of an element
U_BY_QUALITY = {
    "moyenne": {"walls": 0.8, "roof": 0.4, "floor": 0.8, "windows": 2.6},
    "bonne": {"walls": 0.4, "roof": 0.25, "floor": 0.4, "windows": 1.8},
    "tres bonne": {"walls": 0.25, "roof": 0.15, "floor": 0.25, "windows": 1.4},
}

# Insulation works: element improved and U value reached
WORK_TARGETS = {
    "iti": ("walls", 0.30),  # R ~ 3.7 with remaining thermal bridges
    "roof": ("roof", 0.15),  # R ~ 7
    "floor_ceiling": ("floor", 0.30),  # R ~ 3
    "windows": ("windows", 1.3),  # Double glazing, Uw 1.3
}
# Humidity-controlled mechanical ventilation vs uncontrolled air renewal
VMC_AIR_FACTOR = 0.75

FLOOR_HEIGHT = 2.5
WINDOW_RATIO = 0.18  # Glazed area / living surface
WINDOW_UNIT_AREA = 1.8  # m2 per window
FLOOR_TEMPERATURE_FACTOR = 0.45  # Floor over crawl space / ground loses less than walls
THERMAL_BRIDGES_SHARE = 0.10  # Of transmission losses
# An apartment has roughly half of its perimeter on the outside, and a 1 in 4
# chance to be on the top floor or on the ground floor
APARTMENT_EXPOSED_PERIMETER = 0.5
APARTMENT_ROOF_FLOOR_EXPOSURE = 0.25

# Share of the 5-usage final consumption going to heating and hot water, by period
HEATING_SHARE_BY_PERIOD = [0.75, 0.75, 0.70, 0.70, 0.62, 0.55]
HOT_WATER_SHARE_BY_PERIOD = [0.15, 0.15, 0.17, 0.18, 0.23, 0.28]


def construction_year(year: Optional[int], period: Optional[str]) -> Optional[int]:
    if year:
        return year
    years = [int(y) for y in re.findall(r"(1[89]\d\d|20\d\d)", period or "")]
    if not years:
        return None
    if "avant" in (period or "").lower():
        return years[0] - 1
    return years[0]


def period_index(year: Optional[int], period: Optional[str]) -> int:
    y = construction_year(year, period)
    if y is None:
        return 1  # Unknown: assume the most common case, 1948-1974, uninsulated
    for i, bound in enumerate(PERIOD_BOUNDS):
        if y <= bound:
            return i
    return len(PERIOD_BOUNDS)


def normalize_quality(quality: Optional[str]) -> Optional[str]:
    if not quality:
        return None
    q = quality.lower().replace("è", "e").replace("é", "e").strip()
    return q if q in U_BY_QUALITY or q == "insuffisante" else None


class Envelope:
    def __init__(self, surface: float, building_type: Optional[str], year: Optional[int] = None,
                 period: Optional[str] = None, qualities: Optional[Dict[str, Optional[str]]] = None,
                 dpe_losses: Optional[Dict[str, Optional[float]]] = None,
                 exposed_elements: Iterable[str] = ()):
        self.surface = surface
        self.house = "appartement" not in (building_type or "").lower()
        # Apartment elements known to be exposed (top floor roof, ground floor)
        self.exposed = set(exposed_elements)
        self.period = period_index(year, period)
        self.areas = self._geometry()
        self.u = self._u_values(qualities or {})
        self.dpe_losses = self._valid_dpe_losses(dpe_losses)

    # --- Geometry ---

    def _geometry(self) -> Dict[str, float]:
        windows = WINDOW_RATIO * self.surface
        if self.house:
            levels = 1 if self.surface <= 100 else 2
            footprint = self.surface / levels
            gross_walls = 4 * math.sqrt(footprint) * FLOOR_HEIGHT * levels
            roof = floor = footprint
        else:
            gross_walls = 4 * math.sqrt(self.surface) * FLOOR_HEIGHT * APARTMENT_EXPOSED_PERIMETER
            roof = self.surface * (1 if "roof" in self.exposed else APARTMENT_ROOF_FLOOR_EXPOSURE)
            floor = self.surface * (1 if "floor" in self.exposed else APARTMENT_ROOF_FLOOR_EXPOSURE)
        return {
            "walls": max(gross_walls - windows, 0.0),
            "roof": roof,
            "floor": floor,
            "windows": windows,
            "volume": self.surface * FLOOR_HEIGHT,
        }

    @property
    def wall_area(self) -> float:
        return self.areas["walls"]

    @property
    def walls_uninsulated(self) -> bool:
        return self.u["walls"] >= 2.0

    @property
    def window_count(self) -> int:
        return max(2, round(self.areas["windows"] / WINDOW_UNIT_AREA))

    def _u_values(self, qualities: Dict[str, Optional[str]]) -> Dict[str, float]:
        u = {element: values[self.period] for element, values in U_BY_PERIOD.items()}
        for element in u:
            quality = normalize_quality(qualities.get(element))
            if quality in U_BY_QUALITY:
                u[element] = min(u[element], U_BY_QUALITY[quality][element])
        return u

    @staticmethod
    def _valid_dpe_losses(losses: Optional[Dict[str, Optional[float]]]) -> Optional[Dict[str, float]]:
        if not losses:
            return None
        clean = {k: float(v) for k, v in losses.items() if k in ELEMENTS and v is not None and v >= 0}
        if set(clean) != set(ELEMENTS) or sum(clean.values()) <= 0:
            return None
        return clean

    # --- Losses ---

    def _estimated_losses(self) -> Dict[str, float]:
        a = self.areas
        losses = {
            "walls": self.u["walls"] * a["walls"],
            "roof": self.u["roof"] * a["roof"],
            "floor": self.u["floor"] * a["floor"] * FLOOR_TEMPERATURE_FACTOR,
            "windows": self.u["windows"] * a["windows"],
            "air": 0.34 * AIR_CHANGE_BY_PERIOD[self.period] * a["volume"],
        }
        transmission = losses["walls"] + losses["roof"] + losses["floor"] + losses["windows"]
        losses["bridges"] = THERMAL_BRIDGES_SHARE * transmission
        return losses

    def losses(self, works: List[str] = ()) -> Dict[str, float]:
        """Heat losses (W/K) per element after the given works."""
        losses = dict(self.dpe_losses or self._estimated_losses())
        for work in works:
            if work in WORK_TARGETS:
                element, u_new = WORK_TARGETS[work]
                # Never worse than the current state
                losses[element] *= min(1.0, u_new / self.u[element])
            elif work == "vmc":
                losses["air"] *= VMC_AIR_FACTOR
        return losses

    def shares(self) -> Dict[str, float]:
        losses = self.losses()
        total = sum(losses.values())
        return {k: v / total for k, v in losses.items()}

    def heating_reduction(self, works: List[str]) -> float:
        """Relative reduction of the heating need brought by the works."""
        before = sum(self.losses().values())
        after = sum(self.losses(works).values())
        return 1 - after / before if before > 0 else 0.0

    @property
    def heating_share(self) -> float:
        return HEATING_SHARE_BY_PERIOD[self.period]

    @property
    def hot_water_share(self) -> float:
        return HOT_WATER_SHARE_BY_PERIOD[self.period]
