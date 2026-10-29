"""Owner's and buyer's files of a dwelling, in the site's identity: a navy
cover with brass corner marks (the dashboard's tiles), then light pages that
print well.

- Owner (« Avis de valeur préparatoire »): an estate agent's market analysis,
  no works. Their address and value first; a synthesis; the commune's market
  (median price, trend, number of sales, nearby communes); the comparable
  sales on a price axis; how the value is built and what the visit will
  settle; the DPE in the sale (price gaps measured in the department, legal
  file, rentals); the pricing strategy; then one low-commitment step (a free
  visit, no obligation to sell) with the advisor's contact and a QR code.
- Buyer (« Dossier acheteur »): projecting into the project. Before / after
  (class, consumption, energy bill), the works item by item with what each
  treats, how the site unfolds, the financing month by month, and what the
  dwelling will be worth.

Every figure comes from the file (DVF, ADEME DPE, SPREA's simulation): nothing
is invented, and each estimate says so.
"""
from datetime import date
from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (CondPageBreak, Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

try:
    from api.pdf_service import (BRASS, BRASS_LIGHT, CONTENT_W, CORAL, DPE_COLORS, FAINT, HEADER_H, INK, IVORY, LABELS,
                                 LINE, MARGIN, MUTED, NAVY, NBSP, PAGE_H, PAGE_W, SAGE, S, TINT, WHITE, NumberedCanvas,
                                 bullet_list, comparables_table, days, eur, eur_range, grid, head, kv, num, rows_table,
                                 section, share_bars, style, text)
    from api.report_content import LOSS_NAMES, WORK_ORDER
except ImportError:
    from pdf_service import (BRASS, BRASS_LIGHT, CONTENT_W, CORAL, DPE_COLORS, FAINT, HEADER_H, INK, IVORY, LABELS,
                             LINE, MARGIN, MUTED, NAVY, NBSP, PAGE_H, PAGE_W, SAGE, S, TINT, WHITE, NumberedCanvas,
                             bullet_list, comparables_table, days, eur, eur_range, grid, head, kv, num, rows_table,
                             section, share_bars, style, text)
    from report_content import LOSS_NAMES, WORK_ORDER

PANEL = colors.HexColor('#0D1424')
PANEL_LINE = colors.HexColor('#2A3346')
ON_DARK = colors.HexColor('#ECEFF4')
ON_DARK_MUTED = colors.HexColor('#97A1B3')

NOTICE = ("Estimations indicatives établies à partir des ventes DVF et du DPE publié : "
          "ni expertise immobilière, ni audit énergétique.")

# What each work treats, as named in the heat losses of the DPE
WORK_TREATS = {"roof": "roof", "iti": "walls", "ite": "walls", "floor_ceiling": "floor", "windows": "windows", "vmc": "air"}
WORK_GAIN = {
    "pac_air_eau": "Remplace le chauffage actuel : jusqu'à trois fois moins d'énergie pour la même chaleur.",
    "heating": "Chauffage électrique plus économe, chaleur plus douce et régulière.",
    "ecs": "Eau chaude produite avec environ trois fois moins d'électricité.",
}


def fr(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace('.', ',')


def pct(x: float) -> str:
    return f"{round(x)}{NBSP}%"


def dark(name: str, **kw):
    return style(name, **{'textColor': ON_DARK, **kw})


D = {
    'kicker': dark('d_kicker', fontSize=9, leading=12, textColor=BRASS_LIGHT),
    'title': dark('d_title', fontName='Serif-SemiBold', fontSize=30, leading=35),
    'sub': dark('d_sub', fontName='Serif', fontSize=15, leading=20, textColor=ON_DARK_MUTED),
    'meta': dark('d_meta', fontSize=9, leading=13, textColor=ON_DARK_MUTED),
    'label': dark('d_label', fontSize=7.5, leading=10, textColor=ON_DARK_MUTED),
    'kpi': dark('d_kpi', fontName='Serif-SemiBold', fontSize=21, leading=25),
    'kpi_gold': dark('d_kpi_gold', fontName='Serif-SemiBold', fontSize=21, leading=25, textColor=BRASS_LIGHT),
    'small': dark('d_small', fontSize=8, leading=11, textColor=ON_DARK_MUTED),
    'body': dark('d_body', fontSize=10, leading=15),
    'lead': dark('d_lead', fontName='Serif', fontSize=13, leading=18),
    'cta': dark('d_cta', fontName='Serif-SemiBold', fontSize=15, leading=19, textColor=BRASS_LIGHT),
}
L = {
    'lead': style('l_lead', fontName='Serif', fontSize=12, leading=17),
    'kpi': style('l_kpi', fontName='Serif-SemiBold', fontSize=17, leading=21),
    'kpi_gold': style('l_kpi_gold', fontName='Serif-SemiBold', fontSize=17, leading=21, textColor=BRASS),
    'center': style('l_center', alignment=1),
    'center_b': style('l_center_b', alignment=1, fontName='Inter-SemiBold'),
    'step_n': style('l_step_n', fontName='Serif-SemiBold', fontSize=14, leading=16, textColor=BRASS, alignment=1),
}


class Corners(Flowable):
    """A tile of the dashboard: its content, with brass marks on the top-left
    and bottom-right corners."""

    def __init__(self, inner: Flowable, size: float = 12, color=BRASS_LIGHT, weight: float = 1.6):
        super().__init__()
        self.inner, self.size, self.color, self.weight = inner, size, color, weight

    def wrap(self, aw, ah):
        self.w, self.h = self.inner.wrap(aw, ah)
        return self.w, self.h

    def draw(self):
        self.inner.drawOn(self.canv, 0, 0)
        c, s = self.canv, self.size
        c.saveState()
        c.setStrokeColor(self.color)
        c.setLineWidth(self.weight)
        c.line(0, self.h, s, self.h)
        c.line(0, self.h, 0, self.h - s)
        c.line(self.w, 0, self.w - s, 0)
        c.line(self.w, 0, self.w, s)
        c.restoreState()


def tile(content: List[Any], width: float, on_dark: bool, highlight: bool = False) -> Corners:
    t = Table([[content]], colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PANEL if on_dark else (TINT if highlight else WHITE)),
        ('BOX', (0, 0), (-1, -1), 0.6, PANEL_LINE if on_dark else LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 11), ('RIGHTPADDING', (0, 0), (-1, -1), 11),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 11),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return Corners(t, color=BRASS_LIGHT if on_dark or highlight else BRASS, weight=1.6 if on_dark or highlight else 1.1)


def tiles_row(cells: List[List[Any]], on_dark: bool, highlight: Optional[int] = None, gap: float = 8) -> Table:
    n = len(cells)
    w = (CONTENT_W - gap * (n - 1)) / n
    row = []
    for i, c in enumerate(cells):
        row.append(tile(c, w, on_dark, highlight == i))
        if i < n - 1:
            row.append('')
    widths = []
    for i in range(n):
        widths.append(w)
        if i < n - 1:
            widths.append(gap)
    t = Table([row], colWidths=widths)
    t.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                           ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    return t


def kpi(label: str, value: str, sub: str = '', on_dark: bool = True, gold: bool = False) -> List[Any]:
    st = (D if on_dark else L)
    out = [Paragraph(text(label).upper(), D['label'] if on_dark else style('lab', fontSize=7, leading=9, textColor=MUTED)),
           Spacer(1, 5), Paragraph(value, st['kpi_gold'] if gold else st['kpi'])]
    if sub:
        out += [Spacer(1, 3), Paragraph(sub, D['small'] if on_dark else S['muted'])]
    return out


def badge(label: Optional[str], size: float = 1.15 * cm, font: float = 17) -> Table:
    label = (label or '?').upper()
    bg, fg = DPE_COLORS.get(label, ('#CBD5E1', '#0A0F1A'))
    t = Table([[Paragraph(label, style(f'b{label}{size}', fontName='Inter-SemiBold', fontSize=font, leading=font + 2,
                                       alignment=1, textColor=colors.HexColor(fg)))]], colWidths=[size], rowHeights=[size])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg)), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('ROUNDEDCORNERS', [4, 4, 4, 4])]))
    return t


def label_change(current: str, target: str, on_dark: bool) -> Table:
    arrow = Paragraph('→', style('arr', fontName='Serif-SemiBold', fontSize=18, alignment=1,
                                 textColor=BRASS_LIGHT if on_dark else BRASS))
    t = Table([[badge(current), arrow, badge(target)]], colWidths=[1.25 * cm, 0.9 * cm, 1.25 * cm])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                           ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    return t


def qr(data: str, size: float = 2.6 * cm) -> Drawing:
    widget = QrCodeWidget(data, barLevel='M')
    x0, y0, x1, y1 = widget.getBounds()
    d = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    widget.barFillColor = NAVY
    d.add(widget)
    return d


def tel_uri(phone: str) -> Optional[str]:
    digits = ''.join(ch for ch in phone if ch.isdigit() or ch == '+')
    if digits.startswith('0') and len(digits) == 10:
        digits = '+33' + digits[1:]
    return f"tel:{digits}" if len(digits) >= 10 else None


def facts_line(d: Dict[str, Any]) -> str:
    return ' · '.join(x for x in [
        text(d.get('kind') or 'Logement'), f"{d['surface']:g}".replace('.', ',') + f"{NBSP}m²", text(d.get('period') or ''),
        f"DPE {text(d['label'])} du {date.fromisoformat(d['dpe_date']).strftime('%d/%m/%Y')}" if d.get('dpe_date') else f"DPE {text(d['label'])}",
    ] if x)


def value_range(d: Dict[str, Any], market: Dict[str, Any]) -> Optional[Dict[str, int]]:
    """Where half of the comparable sales stand, brought to this dwelling:
    the spread that the state, floor, outdoor space and fittings explain, and
    that only a visit settles."""
    median, q25, q75 = market.get('price_per_m2'), market.get('q25'), market.get('q75')
    if not median or not q25 or not q75 or q75 <= q25:
        return None
    low, high = round(d['price'] * q25 / median, -3), round(d['price'] * q75 / median, -3)
    return {"low": int(low), "high": int(high)} if high > low else None


def department_name(v: Dict[str, Any]) -> str:
    return "dans votre département" if v.get('class_scope') == 'department' else "en France"


def comparables_note(market: Dict[str, Any]) -> str:
    return f"{num(market['sales'])} ventes {text(market['scope'])} ({text(market['period'])}). Source : {text(market['source'])} (DVF, DGFiP)."


def cover_canvas(canv, doc):
    """Navy cover: the dashboard's background and a thin brass frame."""
    canv.saveState()
    canv.setFillColor(NAVY)
    canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canv.setFillColor(colors.HexColor('#101A2E'))
    canv.circle(PAGE_W * 0.85, PAGE_H * 0.86, 7.5 * cm, fill=1, stroke=0)
    canv.setFillColor(NAVY)
    canv.circle(PAGE_W * 0.85, PAGE_H * 0.86, 6.9 * cm, fill=1, stroke=0)
    canv.setStrokeColor(colors.HexColor('#1C2638'))
    canv.setLineWidth(0.8)
    for r in (2.2, 4.0, 5.8):
        canv.circle(PAGE_W * 0.85, PAGE_H * 0.86, r * cm, fill=0, stroke=1)
    canv.setStrokeColor(BRASS_LIGHT)
    canv.setLineWidth(1.4)
    m, s = 0.9 * cm, 1.4 * cm
    for x, y, dx, dy in ((m, PAGE_H - m, 1, -1), (PAGE_W - m, PAGE_H - m, -1, -1), (m, m, 1, 1), (PAGE_W - m, m, -1, 1)):
        canv.line(x, y, x + dx * s, y)
        canv.line(x, y, x, y + dy * s)
    canv.restoreState()


def light_canvas(canv, doc):
    canv.saveState()
    canv.setFillColor(IVORY)
    canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canv.restoreState()


class CoverCanvas(NumberedCanvas):
    """Header and footer on every page but the cover."""

    def _decorate(self, total: int):
        if self._pageNumber == 1:
            return
        super()._decorate(total)


def advisor_block(agency: Dict[str, Any], on_dark: bool, call: str) -> Optional[Table]:
    name = agency.get('agent_name') or ''
    firm = agency.get('agency_name') or ''
    phone, email = agency.get('phone') or '', agency.get('email') or ''
    if not (name or firm or phone or email):
        return None
    st = D if on_dark else {'body': S['body'], 'small': S['muted'], 'cta': style('cta_l', fontName='Serif-SemiBold', fontSize=14, leading=18, textColor=BRASS)}
    lines: List[Any] = [Paragraph(call, st['cta']), Spacer(1, 6)]
    who = ' · '.join(text(x) for x in (name, firm) if x)
    if who:
        lines.append(Paragraph(f"<b>{who}</b>", st['body']))
    contact = ' · '.join(text(x) for x in (phone, email) if x)
    if contact:
        lines.append(Paragraph(contact, st['body']))
    uri = tel_uri(phone) if phone else (f"mailto:{email}" if email else None)
    left_w = CONTENT_W - 3.6 * cm if uri else CONTENT_W
    cells = [[lines]]
    widths = [left_w]
    if uri:
        code = Table([[qr(uri)], [Paragraph('Appeler' if phone else 'Écrire', style('qrl', fontSize=7, alignment=1,
                                                                                      textColor=ON_DARK_MUTED if on_dark else MUTED))]],
                     colWidths=[3.0 * cm])
        code.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('BACKGROUND', (0, 0), (0, 0), WHITE),
                                  ('TOPPADDING', (0, 0), (0, 0), 6), ('BOTTOMPADDING', (0, 0), (0, 0), 4)]))
        cells[0].append(code)
        widths.append(CONTENT_W - left_w)
    t = Table(cells, colWidths=widths)
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 12),
                           ('RIGHTPADDING', (0, 0), (-1, -1), 12), ('TOPPADDING', (0, 0), (-1, -1), 12),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                           ('BACKGROUND', (0, 0), (-1, -1), PANEL if on_dark else WHITE),
                           ('BOX', (0, 0), (-1, -1), 0.8, BRASS_LIGHT if on_dark else LINE)]))
    return Corners(t)


def build(d: Dict[str, Any], story: List[Any], title: str) -> bytes:
    buffer = BytesIO()
    agency = d.get('agency') or {}
    brand = agency.get('agency_name') or 'SPREA'
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=HEADER_H + 1.0 * cm, bottomMargin=2.3 * cm,
                            title=f"{title} – {d['address']['full']}", author=brand)
    doc.build(story, onFirstPage=cover_canvas, onLaterPages=light_canvas,
              canvasmaker=lambda *a, **k: CoverCanvas(*a, address=d['address']['full'], brand=brand, subtitle=title,
                                                      notice=NOTICE, **k))
    return buffer.getvalue()


def cover_head(d: Dict[str, Any], kicker: str, headline: str) -> List[Any]:
    address = d['address']
    story: List[Any] = [Spacer(1, 0.4 * cm), Paragraph(text(kicker).upper(), D['kicker']), Spacer(1, 10),
                        Paragraph(headline, D['title']), Spacer(1, 6), Paragraph(text(address['street']), D['sub'])]
    if address.get('locality'):
        story.append(Paragraph(text(address['locality']), D['sub']))
    story += [Spacer(1, 8), Paragraph(facts_line(d), D['meta'])]
    if d.get('client_name'):
        story.append(Paragraph(f"Établi pour {text(d['client_name'])}", D['meta']))
    return story


def method(agency: Dict[str, Any]) -> List[Any]:
    return [*bullet_list([
        "Valeur actuelle : prix au m² des ventes comparables (DVF), corrigé de l'écart de prix mesuré entre classes DPE sur les ventes du département.",
        "Valeur après travaux : même méthode à la classe atteinte, en ne retenant que 70 % de l'écart entre classes, et un gain "
        "qui ne dépasse jamais deux fois le coût des travaux.",
        "Travaux, factures d'énergie et aides : moteur de simulation SPREA à partir du DPE publié par l'ADEME, prix moyens du marché "
        "et barème des aides en vigueur (catégorie de revenus par défaut).",
        "Estimation indicative : ni expertise immobilière, ni audit énergétique. Visite, diagnostics et devis d'artisans RGE restent indispensables.",
    ], 'muted')]


# --- Owner's file: a market analysis, by an estate agent ---

# National benchmarks quoted in the pricing strategy (to refresh with the barometers)
MARKET_BENCHMARK = ("Baromètres nationaux 2025-2026 (Laforêt, Interkab) : environ 100 jours pour vendre "
                    "un logement en France, et 4 à 5 % d'écart moyen entre le prix affiché et le prix signé.")


def trend_text(years: List[Dict[str, Any]]) -> Optional[str]:
    if len(years) < 2:
        return None
    first, last = years[0], years[-1]
    change = 100 * (last['m2'] - first['m2']) / first['m2']
    if abs(change) < 1:
        return f"stable entre {first['year']} et {last['year']}"
    return f"{'+' if change > 0 else '−'}{NBSP}{fr(abs(change))}{NBSP}% entre {first['year']} et {last['year']}"


def price_strip(comps: List[Dict[str, Any]], subject_m2: float, low_m2: Optional[float], high_m2: Optional[float]) -> Drawing:
    """The comparable sales on one axis of price per m2, the dwelling's
    estimate and its range on top: where it stands, at a glance."""
    width, height = CONTENT_W, 2.6 * cm
    values = [c.get('adjusted_m2') or c['price_m2'] for c in comps if c.get('price_m2')]
    lo = min(values + [subject_m2] + ([low_m2] if low_m2 else []))
    hi = max(values + [subject_m2] + ([high_m2] if high_m2 else []))
    pad = max(1.0, (hi - lo) * 0.12)
    lo, hi = lo - pad, hi + pad
    x0, x1, y = 0.4 * cm, width - 0.4 * cm, 1.15 * cm

    def X(v):
        return x0 + (v - lo) / (hi - lo) * (x1 - x0)
    d = Drawing(width, height)
    from reportlab.graphics.shapes import Circle, Line, Rect, String
    d.add(Line(x0, y, x1, y, strokeColor=LINE, strokeWidth=1))
    if low_m2 and high_m2:
        d.add(Rect(X(low_m2), y - 7, X(high_m2) - X(low_m2), 14, fillColor=TINT, strokeColor=None))
    for v in values:
        d.add(Circle(X(v), y, 3.4, fillColor=colors.HexColor('#97A1B3'), strokeColor=WHITE, strokeWidth=0.8))
    sx = X(subject_m2)
    d.add(Line(sx, y - 12, sx, y + 12, strokeColor=BRASS, strokeWidth=2))
    d.add(String(sx, y + 17, f"Votre bien : {eur(subject_m2)} /m²", fontName='Inter-SemiBold', fontSize=7.5,
                 fillColor=INK, textAnchor='middle'))
    for v in (lo + pad, hi - pad):
        d.add(String(X(v), y - 22, f"{eur(v)}", fontName='Inter', fontSize=7, fillColor=FAINT, textAnchor='middle'))
    return d


def rich_bullets(items: List[str]) -> List[Any]:
    """Bullets whose markup is ours (values inside are escaped by text())."""
    out = []
    for item in items:
        row = Table([[Paragraph('–', style('dash_r', textColor=BRASS)), Paragraph(item, S['body'])]],
                    colWidths=[0.45 * cm, CONTENT_W - 0.45 * cm])
        row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                 ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                                 ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5)]))
        out.append(row)
    return out


def owner(d: Dict[str, Any]) -> bytes:
    v, market = d['valuation'], d['market']
    city = d.get('city_market')
    agency = d.get('agency') or {}
    prem = v.get('class_premium') or {}
    rng = value_range(d, market)
    kind = (d.get('kind') or 'logement').lower()
    house = kind.startswith('maison')
    label = d['label']
    surface = d['surface']
    m2_now = v['price_m2_now']
    m2_market = market['price_per_m2']
    adj = 100 * (m2_now - m2_market) / m2_market if m2_market else 0
    kinds = 'maisons' if house else 'appartements'
    who = ' · '.join(text(x) for x in (agency.get('agent_name'), agency.get('agency_name')) if x)

    # Cover: their dwelling, its value, who signs it, one step
    story = cover_head(d, 'Avis de valeur préparatoire · confidentiel', f"Ce que vaut votre {text(kind)} aujourd'hui")
    story += [Spacer(1, 22), tiles_row([
        kpi("Valeur estimée", eur(d['price']),
            f"entre {eur(rng['low'])} et {eur(rng['high'])}" if rng else f"{eur(m2_now)} /m²", gold=True),
        kpi("Prix médian du secteur", f"{eur(m2_market)}<font size='11'> /m²</font>", f"{kinds} comparables, {text(market['scope'])}"),
        kpi("Ventes analysées", num(market['sales']), f"actes notariés, {text(market['period'])}"),
    ], on_dark=True), Spacer(1, 18),
        Paragraph("Une analyse établie à partir des ventes réellement signées chez les notaires autour de votre bien, "
                  "de son DPE et de l'évolution des prix de votre commune.", D['lead']), Spacer(1, 18),
        Paragraph("SOMMAIRE", D['label']), Spacer(1, 5),
        Paragraph("Synthèse · Votre marché local · Les ventes comparables · Le positionnement de votre bien · "
                  "Le DPE dans votre vente · La stratégie de prix · La prochaine étape", D['body']), Spacer(1, 22)]
    block = advisor_block(agency, True, "Affinons cette estimation chez vous : 30 minutes, gratuit, sans engagement de vendre.")
    if block:
        story.append(block)
    story += [Spacer(1, 10), Paragraph("Une estimation ne vous engage à rien : elle vous dit ce que vaut votre bien, que vous vendiez "
                                       "dans trois mois, dans trois ans, ou jamais.", D['small']), PageBreak()]

    n = 0

    def next_section(title: str):
        nonlocal n
        n += 1
        return section(n, title)

    # Synthesis: the four things to remember
    points = [f"<b>Valeur.</b> Votre {text(kind)} de {f'{surface:g}'.replace('.', ',')}{NBSP}m² est estimé{'e' if house else ''} autour de "
              f"<b>{eur(d['price'])}</b>, soit {eur(m2_now)} /m²" + (f", dans une fourchette de {eur(rng['low'])} à {eur(rng['high'])} "
              "que la visite permettra de resserrer." if rng else ".")]
    trend = trend_text(city['years']) if city else None
    if city and city['years']:
        last = city['years'][-1]
        points.append(f"<b>Marché.</b> À {text(city['name'])}, les {kinds} se sont vendu{'e' if house else ''}s {eur(last['m2'])} /m² en médiane "
                      f"en {last['year']}" + (f" ({trend})" if trend else '') + (f", sur {num(last['n'])} ventes : le marché est actif." if last.get('n') else '.'))
    else:
        points.append(f"<b>Marché.</b> {num(market['sales'])} ventes comparables {text(market['scope'])}, médiane {eur(m2_market)} /m².")
    if prem.get(label) is not None and label != 'D':
        points.append(f"<b>DPE.</b> Classé{'e' if house else ''} {text(label)}, votre bien se compare aux ventes de même classe : "
                      f"dans le département, l'écart avec un bien classé D est de {fr(abs(prem[label]), 0)}{NBSP}%. "
                      "Le bon prix en tient compte : c'est ce qui le rend vendable vite.")
    points.append("<b>Stratégie.</b> Un prix juste dès la mise en vente : c'est dans les premières semaines qu'une annonce reçoit le plus "
                  "de visites, et plus elle reste en ligne, plus la négociation est forte.")
    srows = [[Paragraph(str(i + 1), L['step_n']), Paragraph(p, S['body'])] for i, p in enumerate(points)]
    synth = Table(srows, colWidths=[1.0 * cm, CONTENT_W - 1.0 * cm])
    synth.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.5, LINE),
                               ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    story += [Paragraph('Synthèse', S['h2']), Spacer(1, 6), boxed_line_flow([synth])]

    # 1. Local market
    if city and city['years']:
        cells = [kpi(f"Prix médian {city['years'][-1]['year']}", f"{eur(city['years'][-1]['m2'])}<font size='10'> /m²</font>",
                     f"{kinds}, {text(city['name'])}", on_dark=False)]
        if trend:
            cells.append(kpi('Évolution', trend.split(' entre ')[0], f"entre {city['years'][0]['year']} et {city['years'][-1]['year']}",
                             on_dark=False))
        if city['years'][-1].get('n'):
            cells.append(kpi(f"Ventes en {city['years'][-1]['year']}", num(city['years'][-1]['n']), f"{kinds} vendu{'e' if house else ''}s dans la commune",
                             on_dark=False, gold=True))
        story += [CondPageBreak(9 * cm), Spacer(1, 16), next_section('Votre marché local'), Spacer(1, 8),
                  tiles_row(cells, on_dark=False, highlight=len(cells) - 1), Spacer(1, 10)]
        yrows = [[head('Année'), head('Prix médian /m²', 2), head('Ventes', 2)]] + [
            [Paragraph(str(y['year']), S['body']), Paragraph(eur(y['m2']), S['right']), Paragraph(num(y.get('n') or 0), S['right'])]
            for y in city['years']]
        left = grid(yrows, [CONTENT_W * 0.16, CONTENT_W * 0.17, CONTENT_W * 0.12])
        right_rows = [[head('Communes voisines'), head('Prix médian /m²', 2)]] + [
            [Paragraph(text(c['name']), S['body']), Paragraph(eur(c['m2']), S['right'])] for c in city['near']]
        parts = [left, '']
        widths = [CONTENT_W * 0.45, CONTENT_W * 0.07]
        if city['near']:
            parts.append(grid(right_rows, [CONTENT_W * 0.30, CONTENT_W * 0.18]))
            widths.append(CONTENT_W * 0.48)
        both = Table([parts], colWidths=widths)
        both.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                  ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        typical = (f" La vente type : {fr(city['surface'], 0)}{NBSP}m² "
                   f"pour {eur(city['price'])}." if city.get('surface') and city.get('price') else '')
        story += [both, Spacer(1, 4), Paragraph(f"Ventes de {kinds} de la commune, données DVF (DGFiP), mises à jour le "
                                                f"{text(city.get('updated') or '')}.{typical}", S['small'])]

    # 2. Comparable sales
    story += [CondPageBreak(9 * cm), Spacer(1, 16), next_section('Les ventes comparables'), Spacer(1, 8),
              Paragraph(f"Les acquéreurs de votre secteur ont payé en médiane <b>{eur(m2_market)} /m²</b> pour un bien comparable ; "
                        f"la moitié des ventes se situe entre {eur(market['q25'])} et {eur(market['q75'])} /m².", L['lead']), Spacer(1, 8)]
    if market.get('comparables'):
        story += [price_strip(market['comparables'], m2_now,
                              rng['low'] / surface if rng else None, rng['high'] / surface if rng else None),
                  Paragraph(f"Points gris : les ventes comparables, toutes classes DPE confondues. Trait doré : votre bien en classe {text(label)}"
                            + (", et sa fourchette." if rng else "."), S['small']), Spacer(1, 6),
                  comparables_table(market, market.get('adjusted', 'actualisées' in (market.get('source') or ''))), Spacer(1, 3)]
    story += [Paragraph(comparables_note(market), S['small'])]

    # 3. Positioning: how the value is built
    build_rows = [kv('Prix médian au m² des ventes comparables', eur(m2_market))]
    if abs(adj) >= 0.5:
        build_rows.append(kv(f"Ajustement pour la classe {text(label)} (les ventes comparables mêlent toutes les classes)",
                             f"{'+' if adj > 0 else '−'}{NBSP}{fr(abs(adj))}{NBSP}%"))
    build_rows += [kv('Prix au m² retenu pour votre bien', eur(m2_now)),
                   kv(f"× surface habitable ({f'{surface:g}'.replace('.', ',')}{NBSP}m²)", ''),
                   kv('<b>Valeur estimée</b>', f"<b>{eur(d['price'])}</b>")]
    if rng:
        build_rows.append(kv('Fourchette du secteur (moitié des ventes)', f"{eur(rng['low'])} – {eur(rng['high'])}"))
    criteria = [[head('Ce que la visite vient préciser'), head('Effet sur le prix')]]
    crit = [("État général, prestations, cuisine et salles d'eau", "le premier facteur d'écart avec la médiane"),
            ("Luminosité, exposition, vue, calme", "très recherchés, souvent sous-estimés"),
            (("Terrain, jardin, dépendances" if house else "Étage, ascenseur, balcon ou terrasse"), "écart sensible d'un bien à l'autre"),
            ("Stationnement, garage, cave", "un vrai plus dans la plupart des secteurs"),
            ("Travaux réalisés depuis le DPE", "un nouveau DPE peut améliorer la classe, donc le prix")]
    for a, b in crit:
        criteria.append([Paragraph(a, S['body']), Paragraph(b, S['muted'])])
    story += [CondPageBreak(9 * cm), Spacer(1, 16), next_section('Le positionnement de votre bien'), Spacer(1, 8),
              rows_table(build_rows, [CONTENT_W * 0.66, CONTENT_W * 0.34], bold_last=not rng), Spacer(1, 12),
              KeepTogether([grid(criteria, [CONTENT_W * 0.55, CONTENT_W * 0.45]), Spacer(1, 4),
                            Paragraph("Les chiffres voient les ventes et le DPE ; ils ne voient ni la lumière, ni l'état des pièces, "
                                      "ni les travaux faits depuis. C'est ce que votre conseiller vient apprécier pour fixer le juste prix.",
                                      S['muted'])])]

    # 4. The DPE in the sale (an agent's subject: price, buyers, legal file)
    story += [CondPageBreak(9 * cm), Spacer(1, 16), next_section('Le DPE dans votre vente'), Spacer(1, 8)]
    if prem:
        prow = [[head('Classe DPE'), *[head(c, 1) for c in LABELS]],
                [Paragraph('Écart de prix vs D', S['body']),
                 *[Paragraph(("<b>" if c == label else '') + (f"{prem[c]:+.0f}{NBSP}%".replace('+0', '0').replace('-', '−'))
                             + ("</b>" if c == label else ''), style(f'op{c}', alignment=1)) for c in LABELS]]]
        t = grid(prow, [CONTENT_W * 0.30] + [CONTENT_W * 0.10] * 7)
        i = LABELS.index(label) + 1 if label in LABELS else None
        if i:
            t.setStyle(TableStyle([('BACKGROUND', (i, 0), (i, -1), TINT)]))
        story += [t, Spacer(1, 3), Paragraph(f"{kinds.capitalize()}, écarts mesurés sur {num(v.get('class_sample') or 0)} ventes "
                                             f"rapprochées de leur DPE ({text(v.get('class_period') or '')}).", S['small']), Spacer(1, 8)]
    legal = []
    if house and label in ('E', 'F', 'G'):
        legal.append(f"<b>Audit énergétique obligatoire.</b> Pour vendre une maison classée {text(label)}, un audit doit être remis dès "
                     "la première visite : nous l'organisons avec vous avant la mise en vente.")
    legal.append("<b>Les acquéreurs regardent la classe.</b> Elle figure sur l'annonce et pèse dans leur budget comme dans l'avis de leur banque. "
                 "Un prix aligné sur les ventes de même classe évite la négociation au rabais.")
    if label in ('E', 'F', 'G'):
        legal.append("<b>Si le bien est loué ou destiné à la location.</b> Location interdite pour les logements classés G depuis 2025, "
                     "puis F en 2028 et E en 2034 ; loyers des F et G gelés depuis août 2022. Pour un propriétaire bailleur, "
                     "c'est souvent le bon moment pour arbitrer.")
    legal.append(f"<b>Les bons acquéreurs.</b> Pour un bien classé {text(label)}, nous ciblons ceux qui le recherchent "
                 "(investisseurs, acheteurs prêts à le mettre à leur goût) et leur remettons un dossier qui chiffre leur projet.")
    story += rich_bullets(legal)

    # 5. Pricing strategy
    scen = [[head('Prix de mise en vente'), head('Ce qui se passe en général')],
            [Paragraph(f"<b>Au prix du marché</b><br/><font size='8' color='#5B6577'>autour de {eur(d['price'])}</font>", S['body']),
             Paragraph("Les acquéreurs qui cherchent dans cette gamme voient l'annonce dès sa parution : visites rapides, "
                       "offres proches du prix affiché.", S['muted'])],
            [Paragraph("<b>Juste au-dessus</b><br/><font size='8' color='#5B6577'>3 à 5 %</font>", S['body']),
             Paragraph("Une marge de négociation raisonnable si le bien a des atouts que la visite confirme.", S['muted'])],
            [Paragraph(f"<b>Nettement au-dessus</b><br/><font size='8' color='#5B6577'>10 % et plus, vers {eur(round(d['price'] * 1.1, -3))}</font>", S['body']),
             Paragraph("Peu d'appels : le bien est comparé à de meilleurs biens au même prix. L'annonce s'use, les baisses "
                       "successives font douter, la négociation finale est plus forte.", S['muted'])]]

    story += [CondPageBreak(9 * cm), Spacer(1, 16), next_section('La stratégie de prix'), Spacer(1, 8),
              Paragraph("Le prix d'annonce décide qui voit votre bien : les acquéreurs cherchent par tranche de prix et comparent. "
                        "Les premières semaines sont celles où l'annonce attire le plus de visites.", L['lead']), Spacer(1, 8),
              KeepTogether([grid(scen, [CONTENT_W * 0.32, CONTENT_W * 0.68]), Spacer(1, 4), Paragraph(MARKET_BENCHMARK, S['small'])])]

    # 6. Next step
    steps = [("La visite d'estimation", "30 minutes chez vous : nous relevons ce que les chiffres ne voient pas."),
             ("Votre avis de valeur", "Un prix précis et argumenté, avec les ventes qui le justifient."),
             ("Le plan de mise en vente", "Photos, annonce, diffusion, acquéreurs ciblés, visites qualifiées."),
             ("Jusqu'à la signature", "Offres, compromis, notaire : nous vous accompagnons à chaque étape.")]
    st = Table([[Paragraph(str(i + 1), L['step_n']), Paragraph(f"<b>{a}</b><br/><font color='#5B6577'>{b}</font>", S['body'])]
                for i, (a, b) in enumerate(steps)], colWidths=[1.0 * cm, CONTENT_W - 1.0 * cm])
    st.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.5, LINE),
                            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                            ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    story += [CondPageBreak(9 * cm), Spacer(1, 16), next_section('La prochaine étape'), Spacer(1, 6), st, Spacer(1, 10)]
    block = advisor_block(agency, False, "Prenons rendez-vous pour la visite d'estimation, gratuite et sans engagement.")
    if block:
        story.append(block)
    sources = ("<b>Méthode et sources.</b> Ventes : Demandes de valeurs foncières (DVF, DGFiP), actes notariés rapprochés par type "
               "de bien, surface et distance, prix actualisés au dernier trimestre. DPE : base publique de l'ADEME ; écarts de prix "
               "entre classes mesurés sur les ventes du département rapprochées de leur DPE. Prix de la commune : médianes annuelles DVF. "
               "Avis de valeur préparatoire établi sans visite : il ne remplace ni l'avis de valeur après visite, ni une expertise."
               + (f" Établi par {who}." if who else ''))
    story += [Spacer(1, 12), Paragraph(sources, S['small'])]
    return build(d, story, 'Avis de valeur')


def boxed_line_flow(flowables: List[Any]) -> Table:
    t = Table([[flowables]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), WHITE), ('BOX', (0, 0), (-1, -1), 0.6, LINE),
                           ('LINEBEFORE', (0, 0), (0, -1), 2.5, BRASS_LIGHT),
                           ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                           ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    return t


# --- Buyer's file ---

def buyer(d: Dict[str, Any]) -> bytes:
    v, sim, market, thesis = d['valuation'], d['sim'], d['market'], d['thesis']
    agency = d.get('agency') or {}
    kind = (d.get('kind') or 'logement').lower()
    label, target = d['label'], d['new_label']
    rest = max(0, (d['works'] or 0) - (d['aids'] or 0))
    bill_before, bill_after = sim.get('annual_bill_before'), sim.get('annual_bill_after')
    price_label = 'Prix demandé' if d.get('price_is_asked') else 'Prix estimé'

    story = cover_head(d, 'Dossier acheteur', f"Votre projet, de {text(label)} à {text(target)}")
    cells = [kpi(price_label, eur(d['price']), f"{eur(round(d['price'] / d['surface']))} /m²"),
             kpi('Travaux, aides déduites', eur(rest), f"{eur_range(d['works_low'], d['works_high'])} avant aides")]
    if bill_before and bill_after:
        cells.append(kpi("Facture d'énergie", f"{eur(round(bill_after, -1))}<font size='11'> /an</font>",
                         f"contre {eur(round(bill_before, -1))} aujourd'hui"))
    cells.append(kpi(f"Valeur après travaux", eur(d['resale']), f"classe {text(target)}", gold=True))
    story += [Spacer(1, 22), tiles_row(cells, on_dark=True), Spacer(1, 16)]
    lead = Table([[label_change(label, target, True),
                   Paragraph(f"Le programme : {text(', '.join(n[:1].lower() + n[1:] for n in d['works_names']))}. "
                             f"Environ {days(sim.get('duration_days'))} de chantier, budget complet de <b>{eur(d['total'])}</b> "
                             "achat, notaire et travaux compris, aides déduites.", D['body'])]],
                 colWidths=[3.6 * cm, CONTENT_W - 3.6 * cm])
    lead.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    story += [lead, Spacer(1, 26)]
    block = advisor_block(agency, True, "Visitons-le ensemble, avec ce dossier en main.")
    if block:
        story.append(block)
    story.append(PageBreak())

    n = 0

    def next_section(title: str):
        nonlocal n
        n += 1
        return section(n, title)

    # 1. The project in brief
    source = ("Note rédigée avec l'aide d'une intelligence artificielle (Claude, Anthropic) à partir des seuls chiffres de ce dossier."
              if thesis.get('source') == 'claude' else "Note établie à partir des chiffres de ce dossier.")
    story += [next_section('Le projet en bref'), Spacer(1, 8), Paragraph(text(thesis['these']), L['lead']), Spacer(1, 6),
              *bullet_list(thesis.get('points_forts') or [], 'body'), Spacer(1, 3), Paragraph(source, S['small'])]

    # 2. Before / after
    def row(name: str, before: str, after: str, better: bool = True):
        return [Paragraph(name, S['body']), Paragraph(before, L['center']),
                Paragraph(f"<font color='{'#3E8E63' if better else '#1A2233'}'><b>{after}</b></font>", L['center'])]
    ba = [[head('Votre futur logement'), head("Aujourd'hui", 1), head('Après travaux', 1)],
          [Paragraph('Classe énergie', S['body']), badge(label, 0.8 * cm, 12), badge(target, 0.8 * cm, 12)],
          row('Consommation', f"{num(sim['initial_cep'])} kWh/m²/an", f"{num(sim['new_cep'])} kWh/m²/an")]
    if sim.get('initial_ges') is not None and sim.get('new_ges') is not None:
        ba.append(row('Émissions de CO₂', f"{num(sim['initial_ges'])} kg/m²/an", f"{num(sim['new_ges'])} kg/m²/an"))
    if bill_before and bill_after:
        ba.append(row("Facture d'énergie estimée", f"{eur(round(bill_before, -1))} /an", f"{eur(round(bill_after, -1))} /an"))
        ba.append(row('Soit par mois', f"{eur(round(bill_before / 12))}", f"{eur(round(bill_after / 12))}"))
    if sim.get('heating_need_reduction'):
        ba.append(row('Besoin de chauffage', '—', f"−{NBSP}{pct(sim['heating_need_reduction'] * 100)}"))
    ba.append(row('Location', text(d['rental_now']), text(d['rental_after'])))
    t = grid(ba, [CONTENT_W * 0.34, CONTENT_W * 0.33, CONTENT_W * 0.33])
    t.setStyle(TableStyle([('ALIGN', (1, 1), (-1, 1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('BACKGROUND', (2, 1), (2, -1), colors.HexColor('#F2F7F3'))]))
    story += [CondPageBreak(8 * cm), Spacer(1, 16), next_section('Avant, après'), Spacer(1, 8), t, Spacer(1, 3),
              Paragraph("Facture calculée pour un usage conventionnel du logement (méthode du DPE) aux prix actuels de l'énergie : "
                        "la vôtre dépendra de votre façon d'habiter.", S['small'])]

    # 3. The works, item by item
    shares = sim.get('loss_shares') or {}
    costs = {c['id']: c for c in sim['detailed_costs']}
    ordered = [w for w in WORK_ORDER if w in costs] + [w for w in costs if w not in WORK_ORDER]
    wrows = [[head('Poste'), head('Ce que ça change'), head('Durée', 1), head('Fourchette TTC', 2)]]
    for w in ordered:
        c = costs[w]
        loss = WORK_TREATS.get(w)
        change = (f"Traite {pct(shares[loss] * 100)} des pertes de chaleur ({text(LOSS_NAMES[loss].lower())})" if loss and shares.get(loss)
                  else WORK_GAIN.get(w, ''))
        wrows.append([Paragraph(f"<b>{text(c['name'])}</b>", S['body']), Paragraph(change, S['muted']),
                      Paragraph(days(c.get('days')) if c.get('days') else '–', L['center']),
                      Paragraph(eur_range(c['cost_low'], c['cost_high']), S['right'])])
    wrows.append([Paragraph('<b>Total travaux</b>', S['body']), Paragraph('', S['body']), Paragraph('', S['body']),
                  Paragraph(f"<b>{eur_range(d['works_low'], d['works_high'])}</b>", S['right'])])
    if d['aids']:
        wrows.append([Paragraph('Aides estimées', S['body']), Paragraph("MaPrimeRénov', primes énergie (CEE)", S['muted']),
                      Paragraph('', S['body']), Paragraph(f"<font color='#3E8E63'>−{NBSP}{eur(d['aids'])}</font>", S['right'])])
        wrows.append([Paragraph('<b>Reste à financer</b>', S['body']), Paragraph('', S['body']), Paragraph('', S['body']),
                      Paragraph(f"<b>{eur(rest)}</b>", S['right'])])
    story += [CondPageBreak(8 * cm), Spacer(1, 16), next_section('Les travaux, poste par poste'), Spacer(1, 8),
              grid(wrows, [CONTENT_W * 0.28, CONTENT_W * 0.40, CONTENT_W * 0.11, CONTENT_W * 0.21]), Spacer(1, 3),
              Paragraph("Prix moyens du marché, TVA à 5,5 % : seuls des devis d'artisans RGE fixent le prix réel.", S['small'])]
    if shares:
        losses = sorted(((k, x) for k, x in shares.items() if k in LOSS_NAMES), key=lambda kv: -kv[1])
        story += [Spacer(1, 10), Paragraph('Par où la chaleur s\'échappe aujourd\'hui', S['h3']), Spacer(1, 4),
                  share_bars([{"name": LOSS_NAMES[k], "share": x} for k, x in losses])]

    # 4. How the project unfolds
    steps = [("Avant d'acheter", "Visite avec ce dossier, devis d'artisans RGE pour confirmer les montants, étude de financement."),
             ("Avant les travaux", "Demande des aides avant de signer les devis : MaPrimeRénov' ne finance pas un chantier déjà commencé."
              + (" Pour une rénovation d'ampleur, un Accompagnateur Rénov' agréé suit le projet." if sim.get('aid_pathway') == 'accompagne' else ''))]
    for w in ordered:
        c = costs[w]
        steps.append((text(c['name']), f"Environ {days(c.get('days'))} de chantier." if c.get('days') else ''))
    steps.append(("À la fin", f"Nouveau DPE : classe {text(target)} visée, {text(d['rental_after'].lower())}."))
    srows = [[Paragraph(str(i + 1), L['step_n']), Paragraph(f"<b>{t_}</b><br/><font color='#5B6577'>{x}</font>", S['body'])]
             for i, (t_, x) in enumerate(steps)]
    st = Table(srows, colWidths=[1.0 * cm, CONTENT_W - 1.0 * cm])
    st.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.5, LINE),
                            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                            ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    story += [CondPageBreak(8 * cm), Spacer(1, 16), next_section('Le projet, étape par étape'), Spacer(1, 6),
              Paragraph(f"L'enveloppe d'abord, le chauffage ensuite : c'est l'ordre qui permet de choisir un chauffage à la bonne puissance. "
                        f"Durée totale indicative : {days(sim.get('duration_days'))} de chantier.", S['muted']), Spacer(1, 6), st]

    # 5. Financing, month by month
    rows = [kv(f"{price_label}", eur(d['price'])),
            kv(f"Frais de notaire (environ {round(d['notary_rate'] * 100)}{NBSP}%)", eur(d['notary'])),
            kv('Travaux TTC', eur(d['works']))]
    if d['aids']:
        rows.append(kv('Aides estimées', f"<font color='#3E8E63'>−{NBSP}{eur(d['aids'])}</font>"))
    rows.append(kv('<b>Budget complet</b>', f"<b>{eur(d['total'])}</b>"))
    story += [CondPageBreak(8 * cm), Spacer(1, 16), next_section('Le financement'), Spacer(1, 8),
              rows_table(rows, [CONTENT_W * 0.6, CONTENT_W * 0.4], bold_last=True)]
    ptz, monthly, months = sim.get('eco_ptz_amount'), sim.get('eco_ptz_monthly'), sim.get('eco_ptz_months')
    savings = sim.get('annual_savings')
    if ptz and monthly and months:
        cells = [kpi('Éco-prêt à taux zéro', eur(round(ptz, -2)), f"sans intérêts, sur {round(months / 12)} ans", on_dark=False),
                 kpi('Mensualité', f"{eur(round(monthly))}<font size='10'> /mois</font>", "pour financer les travaux", on_dark=False)]
        if savings:
            cells.append(kpi("Économies d'énergie", f"{eur(round(savings / 12))}<font size='10'> /mois</font>",
                             "estimées, au prix actuel de l'énergie", on_dark=False, gold=True))
        story += [Spacer(1, 10), tiles_row(cells, on_dark=False, highlight=2 if savings else None), Spacer(1, 4)]
        if savings and savings / 12 >= monthly:
            story.append(Paragraph("Les économies d'énergie estimées couvrent la mensualité de l'éco-prêt : les travaux se financent "
                                   "en grande partie par la baisse de la facture.", S['body']))
        story.append(Paragraph("Éco-PTZ sous conditions, accordé par la banque sur devis d'artisans RGE. Le prêt immobilier de l'achat "
                               "peut aussi inclure les travaux.", S['small']))

    # 6. What it will be worth
    rows = [kv(f"Valeur estimée après travaux (classe {text(target)})", f"<b>{eur(d['resale'])}</b>"),
            kv('Fourchette', f"{eur(d['resale_low'])} à {eur(d['resale_high'])}"),
            kv('Prix médian au m² des ventes comparables', eur(market['price_per_m2']))]
    story += [CondPageBreak(7 * cm), Spacer(1, 16), next_section('Ce que vaudra le bien'), Spacer(1, 8),
              rows_table(rows, [CONTENT_W * 0.6, CONTENT_W * 0.4])]
    if market.get('comparables'):
        story += [Spacer(1, 8), Paragraph('Les ventes comparables les plus proches', S['h3']), Spacer(1, 4),
                  comparables_table(market, market.get('adjusted', 'actualisées' in (market.get('source') or '')))]
    story += [Spacer(1, 3), Paragraph(comparables_note(market), S['small'])]
    if d.get('rent_month'):
        story += [Spacer(1, 10), boxed_line(f"Pour le louer : environ <b>{eur(d['rent_month'])} par mois</b> charges comprises "
                                            f"({eur(d['rent_month_low'])} à {eur(d['rent_month_high'])} dans la commune), "
                                            f"{text(d['rental_after'].lower())}.")]

    # 7. Points to check, method, contact
    story += [CondPageBreak(6 * cm), Spacer(1, 16), next_section('Points à vérifier avec votre conseiller'), Spacer(1, 6),
              *bullet_list(thesis.get('risques') or [], 'body')]
    block = advisor_block(agency, False, "Une question sur le projet ? Votre conseiller vous répond.")
    if block:
        story += [Spacer(1, 10), block]
    story += [Spacer(1, 12), Paragraph('Méthode et réserves', S['h3']), Spacer(1, 4), *method(agency)]
    return build(d, story, 'Dossier acheteur')


def boxed_line(markup: str) -> Table:
    t = Table([[Paragraph(markup, S['body'])]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), TINT), ('LINEBEFORE', (0, 0), (0, -1), 2.5, BRASS_LIGHT),
                           ('LEFTPADDING', (0, 0), (-1, -1), 10), ('TOPPADDING', (0, 0), (-1, -1), 8),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    return t
