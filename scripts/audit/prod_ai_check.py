"""End-to-end check of the AI features on the live site, with the shared test
account and a fictitious PV d'AG; the analysis is deleted afterwards."""
import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from scripts.audit.sample_pv import main as make_pv  # noqa: E402

SITE = "https://sprea.vercel.app"
c = httpx.Client(timeout=320)
cfg = c.get(f"{SITE}/api/config").json()
tok = c.post(f"{cfg['supabase_url']}/auth/v1/token?grant_type=password", headers={"apikey": cfg["supabase_anon_key"]},
             json={"email": "test@sprea.invalid", "password": "test"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
print("copro-docs:", {k: v for k, v in c.get(f"{SITE}/api/copro-docs", headers=H).json().items() if k != "analyses"})

make_pv("pv.pdf")
data = open("pv.pdf", "rb").read()
up = c.post(f"{SITE}/api/copro-docs/uploads", headers=H, json={"address": "14 rue des Arts 59800 Lille",
            "files": [{"name": "PV_AG_2025.pdf", "size": len(data), "type": "application/pdf"}]})
print("uploads:", up.status_code, up.text[:200])
up = up.json()
put = c.put(up["uploads"][0]["url"], content=data, headers={"Content-Type": "application/pdf"})
print("put:", put.status_code, put.text[:200])
t = time.time()
res = c.post(f"{SITE}/api/copro-docs/{up['id']}/analyze", headers=H)
print(f"analyze: {res.status_code} en {time.time() - t:.0f} s")
out = res.json()
print(json.dumps(out.get("result") or out, ensure_ascii=False, indent=1)[:6000])
text = json.dumps(out, ensure_ascii=False)
for name in ("Fictif", "Anne Exemple"):
    print(f"nom '{name}' repris :", name in text)
pdf = c.get(f"{SITE}/api/copro-docs/{up['id']}/pdf", headers=H)
print("pdf:", pdf.status_code, len(pdf.content))
if res.status_code == 200:
    print("delete:", c.delete(f"{SITE}/api/copro-docs/{up['id']}", headers=H).json())
else:
    print("analyse en échec gardée pour diagnostic :", up["id"])

mono = c.get(f"{SITE}/api/monopro", headers=H, params={"bbox": "3.07,50.63,3.10,50.65", "owner": "company", "signal": "strong"}).json()
print("immeubles avec signal fort (Lille-Fives):", len(mono.get("buildings", [])), "" if "buildings" in mono else mono)
if mono.get("buildings"):
    b = mono["buildings"][0]
    print(b["address"], b["signal_score"], b["owner"])
    t = time.time()
    ex = c.post(f"{SITE}/api/monopro/{b['id']}/signal/explain", headers=H)
    print(f"explain: {ex.status_code} en {time.time() - t:.0f} s")
    print(json.dumps(ex.json(), ensure_ascii=False, indent=1))
