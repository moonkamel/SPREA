"""PDF of the sale dossier of a whole building (api/monopro_report.py), in the
agency's name, with the look of the other SPREA documents."""
from io import BytesIO
from typing import Any, Dict, List

from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

try:
    from api.pdf_service import (BRASS, BRASS_LIGHT, CONTENT_W, HEADER_H, MARGIN, NBSP, S, NumberedCanvas,
                                 _paper, boxed, bullet_list, dpe_badge, eur, eur_range, grid, head, kpi_cell, kv, num, rows_table,
                                 section, style, text)
except ImportError:
    from pdf_service import (BRASS, BRASS_LIGHT, CONTENT_W, HEADER_H, MARGIN, NBSP, S, NumberedCanvas,
                             _paper, boxed, bullet_list, dpe_badge, eur, eur_range, grid, head, kpi_cell, kv, num, rows_table,
                             section, style, text)


def _units_table(d: Dict[str, Any]) -> Table:
    units = d["units"]
    cells = []
    for l in "ABCDEFG":
        n = units["total"][l]
        cells.append([dpe_badge(l, size=0.75 * cm, font_size=11),
                      Paragraph(f"<b>{n}</b>" if n else "–", style(f'u{l}', fontSize=10, alignment=1))])
    t = Table([[c[0] for c in cells], [c[1] for c in cells]], colWidths=[CONTENT_W / 7] * 7)
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    return t


def generate(d: Dict[str, Any]) -> bytes:
    buffer = BytesIO()
    b, agency = d["building"], d["agency"]
    address = b.get("address") or "Immeuble"
    brand = agency.get("agency_name") or "SPREA"
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=HEADER_H + 1.0 * cm, bottomMargin=2.0 * cm,
                            title=f"Dossier immeuble – {address}", author=brand)
    n = 0

    def next_section(title: str):
        nonlocal n
        n += 1
        return section(n, title)

    owner = d.get("owner") or {}
    company = d.get("company") or {}
    name = company.get("name") or owner.get("name") or ""
    form = owner.get("legal_form") or ""
    # "SCI DU BRUNIOL" already carries its legal form
    owner_name = name if not form or name.upper().startswith(form.upper() + " ") else f"{form} {name}".strip()
    facts = " · ".join(x for x in [
        f"{b['nb_log']} logements", f"{d['levels']} niveaux" if d.get("levels") else None,
        f"construit en {b['year_built']}" if b.get("year_built") else None,
        f"{num(d['shab'])}{NBSP}m² habitables{' (estimés)' if d['shab_estimated'] else ''}",
    ] if x)
    story: List[Any] = [
        Paragraph("Dossier immeuble · arguments de cession", style('kicker', fontSize=9, textColor=BRASS)),
        Paragraph(text(address), S['address']), Spacer(1, 4), Paragraph(text(facts), S['meta']),
    ]
    if owner_name:
        story.append(Paragraph(f"Propriétaire : {text(owner_name)}" + (f" · siège : {text(company['address'])}" if company.get("address") else ""), S['meta']))
    story.append(Spacer(1, 14))

    # Key figures
    v, w = d.get("value"), d.get("works")
    cells = []
    if d.get("worst"):
        g = d["units"]["total"]["G"] + d["units"]["total"]["F"]
        cells.append([*kpi_cell("Logements F ou G", f"<font color='#C4553A'>{g}</font> / {b['nb_log']}", big=True),
                      Paragraph("interdits ou bientôt interdits à la location", style('k1', fontSize=7.5, leading=10, textColor=S['muted'].textColor))])
    if w:
        cells.append([*kpi_cell("Travaux à prévoir", eur_range(w['low'], w['high'])),
                      Paragraph("à la charge du seul propriétaire", style('k2', fontSize=7.5, leading=10, textColor=S['muted'].textColor))])
    if v:
        cells.append([*kpi_cell("Valeur lot par lot", f"≈{NBSP}{eur(v['lots_now'])}"),
                      Paragraph(f"en bloc : {eur(v['block_low'])} à {eur(v['block_high'])}", style('k3', fontSize=7.5, leading=10, textColor=S['muted'].textColor))])
    if cells:
        k = Table([cells], colWidths=[(CONTENT_W - 12) / len(cells)] * len(cells))
        k.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8),
                               ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story += [boxed([k], padding=6), Spacer(1, 14)]

    # 1. Why sell now
    if d["arguments"]:
        story += [next_section("Pourquoi vendre maintenant"), Spacer(1, 6), *bullet_list(d["arguments"]), Spacer(1, 6)]

    # 2. Energy performance of the dwellings
    units = d["units"]
    source = []
    if units["n_known"]:
        source.append(f"{units['n_known']} logement{'s' if units['n_known'] > 1 else ''} avec un DPE publié")
    est = sum(units["estimated"].values())
    if est:
        source.append(f"{est} estimé{'s' if est > 1 else ''} d'après le DPE de l'immeuble")
    if units["unknown"]:
        source.append(f"{units['unknown']} sans information")
    block = [next_section("Le DPE des logements"), Spacer(1, 6), _units_table(d), Spacer(1, 4),
             Paragraph(text(" · ".join(source) or "Aucun DPE publié pour cet immeuble."), S['small']), Spacer(1, 8)]
    ban_rows = [[head("Classe"), head("Interdiction de louer"), head("Logements concernés", 2)]]
    for r in d["rental_ban"]:
        ban_rows.append([Paragraph(r["label"], S['body']),
                         Paragraph(("depuis le " if r["passed"] else "à partir du ") + r["date"], S['body']),
                         Paragraph(f"<b>{r['units']}</b>" if r["units"] else "–", S['right'])])
    block += [grid(ban_rows, [CONTENT_W * 0.2, CONTENT_W * 0.5, CONTENT_W * 0.3]), Spacer(1, 4),
              Paragraph("Loi Climat et Résilience : un logement interdit ne peut plus faire l'objet d'un nouveau bail ni d'un renouvellement. "
                        "Les loyers des logements F et G sont gelés depuis le 24 août 2022.", S['small'])]
    story += [CondPageBreak(8 * cm), Spacer(1, 16), KeepTogether(block)]

    # 3. Works
    if w:
        rows = [[head("Travaux"), head("Constat"), head("Coût TTC", 2)]]
        for it in w["items"]:
            rows.append([Paragraph(text(it["name"]), S['body']), Paragraph(text(it["reason"]), S['muted']),
                         Paragraph(eur_range(it['low'], it['high']), S['right'])])
        rows.append([Paragraph("<b>Total</b>", S['body']), Paragraph("", S['muted']), Paragraph(eur_range(w['low'], w['high']), S['right_b'])])
        story += [CondPageBreak(7 * cm), Spacer(1, 16), KeepTogether([
            next_section("Les travaux à prévoir"), Spacer(1, 6),
            grid(rows, [CONTENT_W * 0.42, CONTENT_W * 0.3, CONTENT_W * 0.28], bold_last=True), Spacer(1, 4),
            Paragraph(("Travaux déduits du DPE (isolation et équipements constatés). " if w["detailed"] else
                       "Ordre de grandeur d'une rénovation énergétique globale pour cette classe. ")
                      + "Coûts moyens de marché ; seuls un audit énergétique et des devis fixent le montant réel. "
                        "En monopropriété, le propriétaire finance seul l'ensemble des travaux.", S['small'])])]

    # 4. Value
    if v:
        rows = [kv("Prix de marché local (appartements)", f"{eur(v['price_m2'])}/m²"),
                kv("Valeur lot par lot, état actuel", f"<b>{eur(v['lots_now'])}</b>", 'right_b'),
                kv("Valeur en bloc (décote usuelle de 15 à 25 %)", eur_range(v['block_low'], v['block_high'])),
                kv(f"Valeur lot par lot après rénovation (classe C)", eur(v['after_works']))]
        if v.get("dpe_discount"):
            rows.append(kv("Décote liée au DPE (par rapport à la classe D)", f"<font color='#C4553A'>−{NBSP}{eur(v['dpe_discount'])}</font>"))
        story += [CondPageBreak(7 * cm), Spacer(1, 16), KeepTogether([
            next_section("Ce que vaut l'immeuble"), Spacer(1, 6), rows_table(rows, [CONTENT_W * 0.62, CONTENT_W * 0.38]), Spacer(1, 4),
            Paragraph(text(f"Prix : {v['source'] or 'ventes DVF voisines'}. Correction selon la classe DPE de chaque logement"
                           + (" (écarts mesurés sur les ventes du département)." if v['measured'] else " (moyenne nationale).")
                           + " Estimation indicative, qui ne remplace pas une expertise."), S['small'])])]

    # 5. Obligations
    # The audit already stands among the reasons to sell when it is required now
    obligations = [x for x in (None if d["audit"].get("required") else d["audit"].get("text"),
                               (d.get("collective_dpe") or {}).get("text")) if x]
    if obligations:
        story += [CondPageBreak(5 * cm), Spacer(1, 16), KeepTogether([next_section("Obligations du propriétaire"), Spacer(1, 6),
                                                                          *bullet_list(obligations, 'muted')])]

    # 6. Owner and contact
    tail: List[Any] = [next_section("Le propriétaire"), Spacer(1, 6)]
    if owner_name:
        lines = [owner_name, f"SIREN {owner.get('siren')}"]
        if company.get("address"):
            lines.append(f"Siège : {company['address']}")
        if d.get("portfolio_count"):
            lines.append(f"Autres immeubles détenus dans la base : {d['portfolio_count']}")
        if d.get("holding"):
            lines.append(d["holding"])
        tail += bullet_list(lines, 'muted')
    contact = " · ".join(x for x in [agency.get("agent_name"), agency.get("phone"), agency.get("email")] if x)
    tail += [Spacer(1, 12), boxed([Paragraph(f"<b>{text(brand)}</b>", S['body']),
                                   Paragraph(text("Estimation de l'immeuble, vente en bloc ou lot par lot, mise en relation avec des investisseurs."), S['muted'])]
                                  + ([Paragraph(text(contact), S['muted'])] if contact else []), rule=BRASS_LIGHT, padding=10),
             Spacer(1, 6),
             Paragraph("Sources publiques : base nationale des bâtiments (CSTB), propriétaires personnes morales (DGFiP), DPE (ADEME), "
                       "ventes DVF (DGFiP), Annuaire des entreprises. Document indicatif, qui ne constitue ni une expertise, "
                       "ni un audit énergétique, ni un conseil juridique.", S['small'])]
    story += [CondPageBreak(6 * cm), Spacer(1, 12), *tail]

    doc.build(story, onFirstPage=_paper, onLaterPages=_paper,
              canvasmaker=lambda *a, **k: NumberedCanvas(*a, address=address, brand=brand, subtitle="Dossier immeuble", **k))
    return buffer.getvalue()
