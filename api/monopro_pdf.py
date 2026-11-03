"""PDF of the dossier of a whole building (api/monopro_report.py), with the look
of the other SPREA documents, for two readers:
- "agent" (the app): the sale dossier, in the agency's name;
- "tce" (the signed link sent to building firms): the same facts read as a
  worksite, works by trade, what weighs on the owner, how to win the job."""
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

try:
    from api.green_value import WORKS_SHARE
    from api.pdf_service import (BRASS, BRASS_LIGHT, CONTENT_W, HEADER_H, MARGIN, NBSP, S, NumberedCanvas,
                                 _paper, boxed, bullet_list, dpe_badge, eur, eur_range, grid, head, kpi_cell, kv, num, rows_table,
                                 section, style, text)
except ImportError:
    from green_value import WORKS_SHARE
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


def pages(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")


def generate(d: Dict[str, Any], audience: str = "agent") -> bytes:
    """Two pages: a long dossier (many works, every argument) is set tighter."""
    render = _render_tce if audience == "tce" else _render
    pdf = render(d, compact=False)
    return pdf if pages(pdf) <= 2 else render(d, compact=True)


def _render(d: Dict[str, Any], compact: bool) -> bytes:
    buffer = BytesIO()
    gap = 6 if compact else 12
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
        f"{b['nb_log']} logement{'s' if b['nb_log'] > 1 else ''}",
        f"{d['levels']} niveau{'x' if d['levels'] > 1 else ''}" if d.get("levels") else None,
        f"construit en {b['year_built']}" if b.get("year_built") else None,
        f"{num(d['shab'])}{NBSP}m² habitables{' (estimés)' if d['shab_estimated'] else ''}",
    ] if x)
    story: List[Any] = [
        Paragraph("Dossier immeuble · arguments de cession", style('kicker', fontSize=9, textColor=BRASS)),
        Paragraph(text(address), S['address']), Spacer(1, 4), Paragraph(text(facts), S['meta']),
    ]
    if owner_name:
        story.append(Paragraph(f"Propriétaire : {text(owner_name)}" + (f" · siège : {text(company['address'])}" if company.get("address") else ""), S['meta']))
    story.append(Spacer(1, gap + 2))

    # Key figures
    v, w = d.get("value"), d.get("works")
    cells = []
    g = d["units"]["total"]["G"] + d["units"]["total"]["F"]
    if g:
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
        story += [boxed([k], padding=6), Spacer(1, gap + 2)]

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
             Paragraph(text(" · ".join(source) or "Aucun DPE publié pour cet immeuble."), S['small']), Spacer(1, gap - 4)]
    ban_rows = [[head("Classe"), head("Interdiction de louer"), head("Logements concernés", 2)]]
    for r in d["rental_ban"]:
        ban_rows.append([Paragraph(r["label"], S['body']),
                         Paragraph(("depuis le " if r["passed"] else "à partir du ") + r["date"], S['body']),
                         Paragraph(f"<b>{r['units']}</b>" if r["units"] else "–", S['right'])])
    block += [grid(ban_rows, [CONTENT_W * 0.2, CONTENT_W * 0.5, CONTENT_W * 0.3]), Spacer(1, 4),
              Paragraph("Loi Climat et Résilience : un logement interdit ne peut plus faire l'objet d'un nouveau bail ni d'un renouvellement. "
                        "Les loyers des logements F et G sont gelés depuis le 24 août 2022.", S['small'])]
    story += [CondPageBreak(8 * cm), Spacer(1, gap), KeepTogether(block)]

    # 3. Works
    if w:
        rows = [[head("Travaux"), head("Constat"), head("Coût TTC", 2)]]
        for it in w["items"]:
            rows.append([Paragraph(text(it["name"]), S['body']), Paragraph(text(it["reason"]), S['muted']),
                         Paragraph(eur_range(it['low'], it['high']), S['right'])])
        rows.append([Paragraph("<b>Total</b>", S['body']), Paragraph("", S['muted']), Paragraph(eur_range(w['low'], w['high']), S['right_b'])])
        story += [CondPageBreak(7 * cm), Spacer(1, gap), KeepTogether([
            next_section("Les travaux à prévoir"), Spacer(1, 6),
            grid(rows, [CONTENT_W * 0.42, CONTENT_W * 0.3, CONTENT_W * 0.28], bold_last=True), Spacer(1, 4),
            Paragraph(("Travaux déduits du DPE (isolation et équipements constatés), complétés pour atteindre la classe C. " if w["detailed"] else
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
        story += [CondPageBreak(7 * cm), Spacer(1, gap), KeepTogether([
            next_section("Ce que vaut l'immeuble"), Spacer(1, 6), rows_table(rows, [CONTENT_W * 0.62, CONTENT_W * 0.38]), Spacer(1, 4),
            Paragraph(text(f"Prix : {v['source'] or 'ventes DVF voisines'}. Correction selon la classe DPE de chaque logement"
                           + (" (écarts mesurés sur les ventes du département)." if v.get('scope') == "department" else
                              " (écarts mesurés sur les ventes nationales)." if v.get('scope') == "national" else " (aucun écart mesuré : pas de correction).")
                           + f" Après rénovation : {round(WORKS_SHARE * 100)}{NBSP}% de l'écart retenus, dans la limite de deux fois le coût des travaux ; le reste tient à l'état général des logements."
                           + " Estimation indicative, qui ne remplace pas une expertise."), S['small'])])]

    # 5. Owner, obligations and contact
    # The audit already stands among the reasons to sell when it is required now
    obligations = [x for x in (None if d["audit"].get("required") else d["audit"].get("text"),
                               (d.get("collective_dpe") or {}).get("text")) if x]
    tail: List[Any] = [next_section("Le propriétaire et ses obligations"), Spacer(1, 6)]
    if owner_name:
        lines = [owner_name, f"SIREN {owner.get('siren')}"]
        if company.get("address"):
            lines.append(f"Siège : {company['address']}")
        if d.get("portfolio_count"):
            lines.append(f"Autres immeubles détenus dans la base : {d['portfolio_count']}")
        tail += bullet_list(lines + obligations, 'muted')
    elif obligations:
        tail += bullet_list(obligations, 'muted')
    contact = " · ".join(x for x in [agency.get("agent_name"), agency.get("phone"), agency.get("email")] if x)
    sources = Paragraph("Sources publiques : base nationale des bâtiments (CSTB), propriétaires personnes morales (DGFiP), DPE (ADEME), "
                        "ventes DVF (DGFiP), Annuaire des entreprises. Document indicatif, qui ne constitue ni une expertise, "
                        "ni un audit énergétique, ni un conseil juridique.", S['small'])
    tail += [Spacer(1, gap - 2), boxed([Paragraph(f"<b>{text(brand)}</b>", S['body']),
                                   Paragraph(text("Estimation de l'immeuble, vente en bloc ou lot par lot, mise en relation avec des investisseurs."), S['muted'])]
                                  + ([Paragraph(text(contact), S['muted'])] if contact else []) + [Spacer(1, 6), sources],
                                  rule=BRASS_LIGHT, padding=6 if compact else 10)]
    story += [CondPageBreak(6 * cm), Spacer(1, gap), *tail]

    doc.build(story, onFirstPage=_paper, onLaterPages=_paper,
              canvasmaker=lambda *a, **k: NumberedCanvas(*a, address=address, brand=brand, subtitle="Dossier immeuble", **k))
    return buffer.getvalue()


# --- Building firms (TCE / RGE): the worksite -------------------------------

# Trades a firm brings to each item of works (api/immeuble.py WORK_NAMES)
TRADES = {
    "facade": "Façadier-isolateur (ITE) ou plâtrier-isolateur (ITI)",
    "roof": "Couvreur, isolation des combles ou rampants",
    "floor": "Isolation des plafonds de caves et parkings",
    "heating": "Chauffagiste (pompe à chaleur, chaudière, régulation)",
    "vmc": "Électricien, ventilation (VMC)",
}
TRADES_OTHER = "Menuisier (fenêtres), chauffagiste, ventilation"
TRADES_GLOBAL = "Tous corps d'état : isolation, menuiseries, chauffage, ventilation"


def trade(item: Dict[str, Any]) -> str:
    if item.get("id") in TRADES:
        return TRADES[item["id"]]
    if item.get("per_dwelling"):
        return "Isolation intérieure, menuiseries, chauffage, ventilation, par logement"
    return TRADES_GLOBAL if item["name"].startswith("Rénovation énergétique globale") else TRADES_OTHER


def owner_pressure(d: Dict[str, Any]) -> List[str]:
    """What forces the owner to act: the law on its dwellings, its obligations."""
    out = []
    t = d["units"]["total"]
    for r in d["rental_ban"]:
        n = r["units"]
        if not n or r["label"] == "E":
            continue
        s = "s" if n > 1 else ""
        out.append(f"{n} logement{s} classé{s} {r['label']} : " +
                   (f"plus de nouveau bail ni de renouvellement depuis le {r['date']}, chaque départ de locataire laisse un "
                    "logement vide." if r["passed"] else f"plus de nouveau bail ni de renouvellement à partir du {r['date']}."))
    if t["F"] + t["G"]:
        out.append("Loyers gelés : le loyer d'un logement F ou G ne peut plus être révisé ni augmenté depuis le 24/08/2022.")
    audit = d.get("audit") or {}
    # The audit depends on the class of the building: only a collective DPE gives it
    if audit.get("required") and d.get("building_dpe"):
        out.append(f"Pour vendre, il doit faire réaliser un audit énergétique (classe {d['label']}) : les travaux deviennent "
                   "visibles de tout acheteur et pèsent sur le prix.")
    cdpe = d.get("collective_dpe") or {}
    if cdpe and not cdpe.get("done"):
        out.append(cdpe["text"])
    return out


def value_pays(d: Dict[str, Any]) -> bool:
    """The value is an argument only when what the works add covers at least their low cost:
    else the owner reads that they cost more than they bring."""
    v, w = d.get("value"), d.get("works_tce")
    return bool(v and w and v["after_works"] - v["lots_now"] >= w["low"])


def officer_name(name: str) -> str:
    """« Christiane TOUPET (BRIQUETEUR) » -> « Christiane TOUPET »: the usual name in brackets is left out."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def label_text(d: Dict[str, Any]) -> Optional[str]:
    """The class of the building only when a collective DPE gives it; else the range of its dwellings."""
    dpe = d.get("building_dpe") or {}
    if dpe.get("label"):
        return f"classé {dpe['label']}" + (f" (DPE collectif du {dpe['date'][8:10]}/{dpe['date'][5:7]}/{dpe['date'][:4]})"
                                           if dpe.get("date") else "")
    units = d["units"]
    present = [l for l in "ABCDEFG" if units["known"][l]]
    if not present:
        return f"classé {d['label']}" if d.get("label") else None
    span = present[0] if len(present) == 1 else f"de {present[0]} à {present[-1]}"
    n, nb = units["n_known"], d["building"]["nb_log"]
    if n < nb:
        # Only some dwellings have a DPE: say so, the others are an estimate
        return (f"{n} logement{'s' if n > 1 else ''} diagnostiqué{'s' if n > 1 else ''} sur {nb} "
                f"(classé{'s' if n > 1 else ''} {span}), pas de DPE collectif")
    return f"logements classés {span}, pas de DPE collectif"


def win_arguments(d: Dict[str, Any]) -> List[str]:
    """What a firm can tell the owner: figures of the dossier, and the RGE label."""
    out = []
    v, w = d.get("value"), d.get("works_tce")
    if value_pays(d):
        if v.get("dpe_discount"):
            out.append(f"Aujourd'hui, l'immeuble vaut environ {eur(v['dpe_discount'])} de moins qu'un immeuble équivalent "
                       "classé D (ventes réelles).")
        out.append(f"Après rénovation (classe C), sa valeur lot par lot passerait d'environ {eur(v['lots_now'])} à "
                   f"{eur(v['after_works'])}, pour {eur_range(w['low'], w['high'])} de travaux.")
    if d["units"]["total"]["F"] + d["units"]["total"]["G"]:
        if d["units"]["total"]["G"]:
            out.append("Les travaux remettent les logements G sur le marché locatif, évitent aux logements F d'en sortir en "
                       "2028 et débloquent la révision des loyers.")
        else:
            out.append("Les travaux évitent aux logements F de sortir du marché locatif le 01/01/2028 et débloquent la "
                       "révision des loyers.")
    out.append("Les primes CEE (certificats d'économies d'énergie) sont ouvertes à tout propriétaire, société comprise, "
               "mais seulement pour des travaux réalisés par une entreprise RGE.")
    out.append("Un seul propriétaire décide : pas d'assemblée générale ni de vote de copropriété avant de lancer le chantier.")
    return out


def _render_tce(d: Dict[str, Any], compact: bool) -> bytes:
    buffer = BytesIO()
    gap = 6 if compact else 12
    b = d["building"]
    address = b.get("address") or "Immeuble"
    brand = "SPREA"
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=HEADER_H + 1.0 * cm, bottomMargin=2.0 * cm,
                            title=f"Dossier chantier – {address}", author=brand)
    n = 0

    def next_section(title: str):
        nonlocal n
        n += 1
        return section(n, title)

    owner = d.get("owner") or {}
    company = d.get("company") or {}
    name = company.get("name") or owner.get("name") or ""
    form = owner.get("legal_form") or ""
    owner_name = name if not form or name.upper().startswith(form.upper() + " ") else f"{form} {name}".strip()
    dpe_txt = label_text(d)
    facts = " · ".join(x for x in [
        f"{b['nb_log']} logement{'s' if b['nb_log'] > 1 else ''}",
        f"{d['levels']} niveau{'x' if d['levels'] > 1 else ''}" if d.get("levels") else None,
        f"construit en {b['year_built']}" if b.get("year_built") else None,
        f"{num(d['shab'])}{NBSP}m² habitables{' (estimés)' if d['shab_estimated'] else ''}",
        dpe_txt,
    ] if x)
    story: List[Any] = [
        Paragraph("Dossier chantier · rénovation énergétique d'un immeuble", style('kicker', fontSize=9, textColor=BRASS)),
        Paragraph(text(address), S['address']), Spacer(1, 4), Paragraph(text(facts), S['meta']),
    ]
    if owner_name:
        story.append(Paragraph(f"Propriétaire unique : {text(owner_name)} (monopropriété, pas de syndic ni de copropriété)", S['meta']))
    story.append(Spacer(1, gap + 2))

    # Key figures: the job, its size, its urgency
    v, w = d.get("value"), d.get("works_tce")
    units = d["units"]
    fg = units["total"]["G"] + units["total"]["F"]
    muted = S['muted'].textColor
    cells = []
    if w:
        cells.append([*kpi_cell("Budget travaux estimé", eur_range(w['low'], w['high'])),
                      Paragraph("coûts moyens de marché, TTC", style('t1', fontSize=7.5, leading=10, textColor=muted))])
    cells.append([*kpi_cell("Surface à traiter", f"{num(d['shab'])}{NBSP}m²"),
                  Paragraph(f"{b['nb_log']} logements" + (f", {d['levels']} niveaux" if d.get("levels") else ""),
                            style('t2', fontSize=7.5, leading=10, textColor=muted))])
    if fg:
        cells.append([*kpi_cell("Logements F ou G", f"<font color='#C4553A'>{fg}</font> / {b['nb_log']}", big=True),
                      Paragraph("interdits ou bientôt interdits à la location"
                                + (f", dont {sum(units['estimated'].values())} estimé{'s' if sum(units['estimated'].values()) > 1 else ''}"
                                   if sum(units['estimated'].values()) else ""),
                                style('t3', fontSize=7.5, leading=10, textColor=muted))])
    k = Table([cells], colWidths=[(CONTENT_W - 12) / len(cells)] * len(cells))
    k.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8),
                           ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story += [boxed([k], padding=6), Spacer(1, gap + 2)]

    # 1. The works, by trade
    if w:
        rows = [[head("Poste"), head("Constat (DPE)"), head("Corps d'état"), head("Coût TTC", 2)]]
        for it in w["items"]:
            rows.append([Paragraph(text(it["name"]), S['body']), Paragraph(text(it["reason"]), S['muted']),
                         Paragraph(text(trade(it)), S['muted']), Paragraph(eur_range(it['low'], it['high']), S['right'])])
        rows.append([Paragraph("<b>Total</b>", S['body']), Paragraph("", S['muted']), Paragraph("", S['muted']),
                     Paragraph(eur_range(w['low'], w['high']), S['right_b'])])
        story += [KeepTogether([
            next_section("Le chantier, poste par poste"), Spacer(1, 6),
            grid(rows, [CONTENT_W * 0.26, CONTENT_W * 0.23, CONTENT_W * 0.26, CONTENT_W * 0.25], bold_last=True), Spacer(1, 4),
            Paragraph(("Postes déduits du DPE (isolation et équipements constatés), complétés pour atteindre la classe C, "
                       "chaque logement au coût de sa propre classe. " if w["detailed"] else
                       "Ordre de grandeur d'une rénovation énergétique de chaque logement, au coût de sa classe. ")
                      + "Coûts moyens de marché : votre visite et vos devis fixent le montant réel. "
                        "Un seul maître d'ouvrage, qui finance seul l'ensemble des travaux.", S['small'])])]

    # 2. The dwellings and the law
    source = []
    if units["n_known"]:
        source.append(f"{units['n_known']} logement{'s' if units['n_known'] > 1 else ''} avec un DPE publié")
    est = sum(units["estimated"].values())
    if est:
        source.append(f"{est} estimé{'s' if est > 1 else ''} " + ("d'après le DPE collectif" if d.get("building_dpe") else f"à la classe du{'s' if units['n_known'] > 1 else ''} DPE publié{'s' if units['n_known'] > 1 else ''}"))
    if units["unknown"]:
        source.append(f"{units['unknown']} sans information")
    block = [next_section("Le DPE des logements"), Spacer(1, 6), _units_table(d), Spacer(1, 4),
             Paragraph(text(" · ".join(source) or "Aucun DPE publié pour cet immeuble."), S['small'])]
    story += [CondPageBreak(5 * cm), Spacer(1, gap), KeepTogether(block)]

    # 3. Why the owner has to act
    pressure = owner_pressure(d)
    if pressure:
        story += [CondPageBreak(5 * cm), Spacer(1, gap), KeepTogether([
            next_section("Pourquoi le propriétaire doit agir"), Spacer(1, 6), *bullet_list(pressure),
            Paragraph("Loi Climat et Résilience : les logements G sont interdits à la location depuis 2025, les F le seront en "
                      "2028 et les E en 2034.", S['small'])])]

    # 4. How to convince the owner, with figures it can check
    args = win_arguments(d)
    value_rows = []
    if value_pays(d):
        value_rows = [kv("Valeur lot par lot, état actuel", eur(v['lots_now'])),
                      kv("Valeur lot par lot après rénovation (classe C)", f"<b>{eur(v['after_works'])}</b>", 'right_b')]
        if v.get("dpe_discount"):
            value_rows.append(kv("Décote liée au DPE (par rapport à la classe D)",
                                 f"<font color='#C4553A'>−{NBSP}{eur(v['dpe_discount'])}</font>"))
    part = [next_section("Vos arguments face au propriétaire"), Spacer(1, 6), *bullet_list(args)]
    if value_rows:
        part += [Spacer(1, 4), rows_table(value_rows, [CONTENT_W * 0.62, CONTENT_W * 0.38]), Spacer(1, 4),
                 Paragraph(text(f"Prix : {v['source'] or 'ventes DVF voisines'} ({eur(v['price_m2'])}/m²), corrigés selon la "
                                "classe DPE de chaque logement. Après rénovation : "
                                f"{round(WORKS_SHARE * 100)}{NBSP}% de l'écart de classe retenus, dans la limite de deux fois le coût "
                                "des travaux. Estimation indicative."), S['small'])]
    story += [CondPageBreak(6 * cm), Spacer(1, gap), KeepTogether(part)]

    # 5. Who to contact
    lines = []
    if owner_name:
        lines += [owner_name, f"SIREN {owner.get('siren') or b.get('owner_siren')}"]
        if company.get("address"):
            lines.append(f"Siège : {company['address']}")
        people = company.get("officers") or []
        # The manager (gérant, président) decides; a partner « indéfiniment responsable » does not
        officer = next((o for o in people if not o.get("company") and re.search(r"(?i)g[ée]rant|pr[ée]sident", o.get("role") or "")), None) \
            or next((o for o in people if re.search(r"(?i)g[ée]rant|pr[ée]sident", o.get("role") or "")), None) \
            or next((o for o in people if not o.get("company")), None) or next(iter(people), None)
        if officer:
            lines.append(f"Dirigeant : {officer_name(officer['name'])}" + (f" ({officer['role']})" if officer.get("role") else ""))
        if d.get("portfolio_count"):
            s = "s" if d["portfolio_count"] > 1 else ""
            lines.append(f"Ce propriétaire détient {d['portfolio_count']} autre{s} immeuble{s} dans la base SPREA : "
                         "un premier chantier peut en appeler d'autres.")
    lines.append("Prise de contact : courrier au siège de la société, à l'attention de son dirigeant, en joignant ce dossier.")
    sources = Paragraph("Sources publiques : base nationale des bâtiments (CSTB), propriétaires personnes morales (DGFiP), DPE (ADEME), "
                        "ventes DVF (DGFiP), Annuaire des entreprises. Document indicatif, qui ne constitue ni une expertise, "
                        "ni un audit énergétique, ni un devis.", S['small'])
    tail = [next_section("Le maître d'ouvrage"), Spacer(1, 6), *bullet_list(lines, 'muted'), Spacer(1, gap - 2),
            boxed([Paragraph("<b>SPREA</b> · chantiers de rénovation repérés pour les entreprises du bâtiment", S['body']),
                   Paragraph(text("D'autres immeubles à rénover près de votre entreprise : contact@sprea.app · sprea.app"), S['muted']),
                   Spacer(1, 6), sources], rule=BRASS_LIGHT, padding=6 if compact else 10)]
    story += [CondPageBreak(6 * cm), Spacer(1, gap), *tail]

    doc.build(story, onFirstPage=_paper, onLaterPages=_paper,
              canvasmaker=lambda *a, **k: NumberedCanvas(*a, address=address, brand=brand, subtitle="Dossier chantier", **k))
    return buffer.getvalue()
