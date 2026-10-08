"""Exports the observatory figures (api/observatoire.build) to
src/data/observatoire.json, read at build time to prerender the public
observatory pages (scripts/seo/prerender.mjs). Run after each green value
update (the monthly workflow does it)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.green_value import load  # noqa: E402
from api.observatoire import build  # noqa: E402

if __name__ == "__main__":
    out = os.path.join(ROOT, "src", "data", "observatoire.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build(load()), f, ensure_ascii=False, separators=(",", ":"))
    print(f"Written {out}")
