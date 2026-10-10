"""PDF of a copropriété documents analysis (api/copro_docs.py), in the
agency's name: the summary an agent hands to a buyer or a notary."""
from datetime import date
from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

try:
    from api.pdf_service import (BRASS, BRASS_LIGHT, CONTENT_W, HEADER_H, MARGIN, S, NumberedCanvas, _paper, boxed,
                                 bullet_list, eur, grid, head, kv, rows_table, section, style, text)
except ImportError:
    from pdf_service import (BRASS, BRASS_LIGHT, CONTENT_W, HEADER_H, MARGIN, S, NumberedCanvas, _paper, boxed,
                             bullet_list, eur, grid, head, kv, rows_table, section, style, text)

RISK_COLORS = {"faible": "#3E8E63", "modéré": "#A8853F", "élevé": "#C4553A"}
LEVEL_COLORS = {"alerte": "#C4553A", "attention": "#A8853F", "info": "#5B6577"}


def _bullets(items: List[str], st: str = 'body') -> List[Any]:
    """bullet_list for items already in Paragraph markup (escaped parts + font tags)."""
    out = bullet_list(["x"] * len(items), st)
    for row, item in zip(out, items):
        row._cellvalues[0][1] = Paragraph(item, S[st])
    return out


def _money(v: Any) -> str:
    return eur(v) if isinstance(v, (int, float)) else "–"


def analysed_on(row: Dict[str, Any], today: date) -> date:
    """Date of the analysis (last update of the row), today when unknown."""
    for key in ("updated_at", "created_at"):
        try:
            return date.fromisoformat(str(row.get(key) or "")[:10])
        except ValueError:
            continue
    return today


def generate(row: Dict[str, Any], agency: Dict[str, Any], today: date) -> bytes:
    r = row["result"]
    buffer = BytesIO()
    copro = r.get("copropriete") or {}
    address = row.get("address") or copro.get("adresse") or "Copropriété"
    brand = agency.get("agency_name") or "SPREA"
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=HEADER_H + 1.0 * cm, bottomMargin=2.0 * cm,
                            title=f"Synthèse copropriété – {address}", author=brand)
    n = 0

    def next_section(title: str):
        nonlocal n
        n += 1
        return section(n, title)

    risk = r.get("niveau_risque") or "modéré"
    meta = " · ".join(x for x in [copro.get("nom"), f"syndic {copro['syndic']}" if copro.get("syndic") else None,
                                  f"{copro['lots']} lots" if copro.get("lots") else None] if x)
    story: List[Any] = [
        Paragraph("Synthèse des documents de copropriété", style('kicker', fontSize=9, textColor=BRASS)),
        Paragraph(text(address), S['address']), Spacer(1, 4),
    ]
    if meta:
        story.append(Paragraph(text(meta), S['meta']))
    story += [Spacer(1, 12), boxed([
        Paragraph(f"Risque pour l'acheteur : <font color='{RISK_COLORS.get(risk, '#5B6577')}'><b>{text(risk)}</b></font>", S['body']),
        Spacer(1, 4), Paragraph(text(r.get("synthese") or ""), S['body'])], padding=10), Spacer(1, 14)]

    if r.get("vigilance"):
        items = [f"<font color='{LEVEL_COLORS.get(v.get('niveau'), '#5B6577')}'><b>{text((v.get('niveau') or '').capitalize())}</b></font> · "
                 f"{text(v.get('point'))} <font color='#8A93A3'>({text(v.get('source'))})</font>" for v in r["vigilance"]]
        story += [next_section("Points de vigilance"), Spacer(1, 6), *_bullets(items), Spacer(1, 10)]

    if r.get("travaux_votes"):
        rows = [[head("Travaux votés"), head("Montant", 2), head("Vote / appels de fonds")]]
        for w in r["travaux_votes"]:
            rows.append([Paragraph(f"{text(w.get('objet'))}<br/><font size=7 color='#8A93A3'>{text(w.get('etat'))} · {text(w.get('source'))}</font>", S['body']),
                         Paragraph(_money(w.get("montant")), S['right']),
                         Paragraph(text(" · ".join(x for x in [w.get("date_vote"), w.get("appels_de_fonds")] if x) or "–"), S['muted'])])
        story += [KeepTogether([next_section("Travaux votés"), Spacer(1, 6),
                                grid(rows, [CONTENT_W * 0.45, CONTENT_W * 0.17, CONTENT_W * 0.38])]), Spacer(1, 10)]

    if r.get("travaux_a_venir"):
        rows = [[head("Travaux à venir (non votés)"), head("Estimation"), head("Échéance")]]
        for w in r["travaux_a_venir"]:
            rows.append([Paragraph(f"{text(w.get('objet'))}<br/><font size=7 color='#8A93A3'>{text(w.get('source'))}</font>", S['body']),
                         Paragraph(text(w.get("estimation") or "–"), S['muted']), Paragraph(text(w.get("horizon") or "–"), S['muted'])])
        story += [KeepTogether([next_section("Travaux à venir"), Spacer(1, 6),
                                grid(rows, [CONTENT_W * 0.5, CONTENT_W * 0.25, CONTENT_W * 0.25])]), Spacer(1, 10)]

    f = r.get("finances") or {}
    fin_rows = [kv(label, _money(f.get(key))) for label, key in (
        ("Budget prévisionnel annuel", "budget_previsionnel"), ("Fonds de travaux", "fonds_travaux"),
        ("Charges impayées des copropriétaires", "impayes_coproprietaires"), ("Dettes fournisseurs", "dettes_fournisseurs"))
        if f.get(key) is not None]
    if fin_rows or f.get("commentaire"):
        block: List[Any] = [next_section("Finances du syndicat"), Spacer(1, 6)]
        if fin_rows:
            block.append(rows_table(fin_rows, [CONTENT_W * 0.62, CONTENT_W * 0.38]))
        if f.get("commentaire"):
            block += [Spacer(1, 4), Paragraph(text(f["commentaire"]) + (f" ({text(f['source'])})" if f.get("source") else ""), S['small'])]
        story += [KeepTogether(block), Spacer(1, 10)]

    if r.get("procedures"):
        items = [text(p.get('objet'))
                 + (f" · syndicat {text(p.get('role_syndicat'))}" if p.get("role_syndicat") not in (None, "", "inconnu") else "")
                 + (f" · {_money(p.get('montant'))}" if p.get("montant") is not None else "")
                 + f" · {text(p.get('etat'))} <font color='#8A93A3'>({text(p.get('source'))})</font>" for p in r["procedures"]]
        story += [next_section("Procédures"), Spacer(1, 6), *_bullets(items), Spacer(1, 10)]

    o = r.get("obligations") or {}
    others = [f"{label} : {o[key]}" for label, key in (("Plan pluriannuel de travaux", "plan_pluriannuel"),
                                                              ("Diagnostic technique global", "dtg"), ("DPE collectif / audit", "dpe_collectif")) if o.get(key)]
    others += list(r.get("vie_copropriete") or [])
    if others:
        story += [next_section("Obligations et vie de la copropriété"), Spacer(1, 6), *bullet_list(others, 'muted'), Spacer(1, 10)]

    if r.get("questions_syndic") or r.get("documents_manquants"):
        block = [next_section("À demander avant le compromis"), Spacer(1, 6),
                 *bullet_list(list(r.get("questions_syndic") or []))]
        if r.get("documents_manquants"):
            block += [Spacer(1, 4), Paragraph("<b>Documents manquants</b>", S['body']),
                      *bullet_list(list(r["documents_manquants"]), 'muted')]
        story += [KeepTogether(block), Spacer(1, 10)]

    docs = " · ".join(f"{d.get('fichier')}" + (f" ({d['date']})" if d.get("date") else "") + ("" if d.get("lisible", True) else " – illisible")
                      for d in r.get("documents") or [])
    contact = " · ".join(x for x in [agency.get("agent_name"), agency.get("phone"), agency.get("email")] if x)
    story += [Spacer(1, 6), boxed([Paragraph(f"<b>{text(brand)}</b>", S['body'])]
                                  + ([Paragraph(text(contact), S['muted'])] if contact else [])
                                  + [Spacer(1, 4), Paragraph(text(f"Documents analysés : {docs}." if docs else ""), S['small']),
                                     Paragraph("Synthèse établie avec l'aide d'une intelligence artificielle (Claude, Anthropic) à partir des seuls "
                                               "documents fournis, le " + analysed_on(row, today).strftime("%d/%m/%Y") + ". Elle ne remplace ni la lecture des "
                                               "documents, ni le pré-état daté, ni l'avis du notaire.", S['small'])],
                                  rule=BRASS_LIGHT, padding=10)]

    doc.build(story, onFirstPage=_paper, onLaterPages=_paper,
              canvasmaker=lambda *a, **k: NumberedCanvas(*a, address=address, brand=brand, subtitle="Synthèse copropriété", **k))
    return buffer.getvalue()
