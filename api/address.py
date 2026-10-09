"""Comparing postal addresses written by different sources (BAN, ADEME,
BDNB, copropriété registry): "18bis" or "18 Bis", "Rue Jean Bart St Pol" or
"Rue Jean Bart (Saint-Pol-sur-Mer)", "che des Grands Bas" or "Chemin des
Grands Bas", accents and apostrophes lost on the way."""
import re
import unicodedata
from typing import Optional, Set, Tuple

# Kinds of street, full and abbreviated: they vary between sources
STREET_KINDS = {
    "rue", "r", "avenue", "av", "ave", "boulevard", "bd", "bld", "bvd", "chemin", "che", "ch", "chem", "place", "pl",
    "impasse", "imp", "allee", "all", "route", "rte", "quai", "cours", "crs", "square", "sq", "residence", "res",
    "rampe", "passage", "pas", "sentier", "sen", "voie", "cite", "faubourg", "fg", "fbg", "promenade", "prom", "villa",
    "hameau", "ham", "lieu", "dit", "parvis", "rond", "point", "rpt", "esplanade", "esp", "mail", "venelle", "ruelle",
    "sente", "carrefour", "car", "lotissement", "lot", "domaine", "dom", "quartier", "qua", "chaussee", "chs",
}
SMALL_WORDS = {"de", "du", "des", "la", "le", "les", "l", "d", "a", "au", "aux", "et", "en", "sur", "sous"}
SAINTS = {"st": "saint", "ste": "sainte"}


def _plain(address: Optional[str]) -> str:
    s = address or ""
    if "â€" in s or "Ã" in s:
        # UTF-8 read as Windows-1252 by a source ("dâ€™Indy", "RÃ©publique")
        try:
            s = s.encode("cp1252", errors="ignore").decode("utf-8", errors="ignore")
        except UnicodeError:
            pass
        s = re.sub(r"â€.?", "'", s)
    s = re.sub(r"[’‘`´]", "'", s)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def address_key(address: Optional[str]) -> str:
    """'121 Rue de Solférino 59800 Lille' -> '121 rue de solferino 59800'."""
    plain = _plain(address)
    # "(Saint-Pol-sur-Mer)": former commune, written by some sources only
    plain = re.sub(r"\([^)]*\)", " ", plain)
    plain = re.sub(r"[^a-z0-9]+", " ", plain).strip()
    # "18bis" and "18 bis"
    plain = re.sub(r"^(\d+) (bis|ter|quater|[a-h])\b", r"\1\2", plain)
    # Up to the postcode: the commune is written in full or not
    m = re.match(r"(.*?\b\d{5})\b", plain)
    return m.group(1) if m else plain


def parts(address: Optional[str]) -> Tuple[Optional[str], Optional[str], Set[str]]:
    """Number (with its suffix), postcode and the distinctive words of the street."""
    words = address_key(address).split()
    if not words:
        return None, None, set()
    number = words[0] if re.match(r"^\d+[a-z]*$", words[0]) else None
    postcode = words[-1] if re.match(r"^\d{5}$", words[-1]) else None
    street = words[1 if number else 0:-1 if postcode else None]
    return number, postcode, {SAINTS.get(w, w) for w in street if w not in STREET_KINDS and w not in SMALL_WORDS}


def same_street(a: Optional[str], b: Optional[str]) -> bool:
    """The distinctive words of one street are all in the other's ("Jean Bart"
    and "Jean Bart St Pol")."""
    _, pa, sa = parts(a)
    _, pb, sb = parts(b)
    if not sa or not sb or (pa and pb and pa != pb):
        return False
    return sa <= sb or sb <= sa


def same_address(a: Optional[str], b: Optional[str]) -> bool:
    na, _, _ = parts(a)
    nb, _, _ = parts(b)
    return bool(na) and na == nb and same_street(a, b)
