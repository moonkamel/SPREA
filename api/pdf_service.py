"""PDF report, in the site's visual identity (navy, brass, Source Serif + Inter).

The page body stays light (ivory) so the report prints well; the navy header
band and brass accents carry the brand.
"""
import os
from datetime import date
from io import BytesIO
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

try:
    from api.figures import display_figures, green_range_shown, r
except ImportError:
    from figures import display_figures, green_range_shown, r

LABELS = ['A', 'B', 'C', 'D', 'E', 'F', 'G']

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

# --- Brand ---

NAVY = colors.HexColor('#0A0F1A')
NAVY_SOFT = colors.HexColor('#111A2B')
IVORY = colors.HexColor('#FBF9F4')
WHITE = colors.HexColor('#FFFFFF')
INK = colors.HexColor('#1A2233')
MUTED = colors.HexColor('#5B6577')
FAINT = colors.HexColor('#8A93A3')
LINE = colors.HexColor('#E4DED1')
BRASS = colors.HexColor('#A8853F')      # darker brass: readable on light paper
BRASS_LIGHT = colors.HexColor('#C9A45C')
TINT = colors.HexColor('#F4EEE1')
SAGE = colors.HexColor('#3E8E63')
CORAL = colors.HexColor('#C4553A')

DPE_COLORS = {
    'A': ('#009C6D', '#FFFFFF'), 'B': ('#52B153', '#FFFFFF'), 'C': ('#78BD76', '#0A0F1A'),
    'D': ('#F4E70F', '#0A0F1A'), 'E': ('#F0B40F', '#0A0F1A'), 'F': ('#EB8235', '#0A0F1A'),
    'G': ('#D7221F', '#FFFFFF'),
}

PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 1.9 * cm

# --- Fonts (SIL Open Font License, see api/fonts/) ---

FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')


def _register_fonts():
    fonts = {
        'Inter': 'Inter-Regular.ttf',
        'Inter-SemiBold': 'Inter-SemiBold.ttf',
        'Serif': 'SourceSerif4-Regular.ttf',
        'Serif-SemiBold': 'SourceSerif4-Semibold.ttf',
    }
    for name, file in fonts.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, file)))
    pdfmetrics.registerFontFamily('Inter', normal='Inter', bold='Inter-SemiBold', italic='Inter', boldItalic='Inter-SemiBold')
    pdfmetrics.registerFontFamily('Serif', normal='Serif', bold='Serif-SemiBold', italic='Serif', boldItalic='Serif-SemiBold')


_register_fonts()

# --- Formatting ---

NBSP = ' '


def eur(value: Optional[float]) -> str:
    return f"{round(value or 0):,}".replace(',', NBSP) + f"{NBSP}€"


def num(value: Optional[float]) -> str:
    return f"{round(value or 0):,}".replace(',', NBSP)


def distance_text(metres: Optional[float]) -> str:
    if metres is None:
        return '–'
    if metres < 1000:
        return f"{round(metres)}{NBSP}m"
    return f"{metres / 1000:.1f}".replace('.', ',') + f"{NBSP}km"


def text(value: Any) -> str:
    """Escapes user or external text before it goes into Paragraph markup."""
    return escape(str(value)) if value not in (None, '') else ''


def style(name: str, **kw) -> ParagraphStyle:
    base = dict(fontName='Inter', fontSize=9.5, leading=14, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    'address': style('address', fontName='Serif-SemiBold', fontSize=22, leading=27),
    'meta': style('meta', fontSize=9.5, textColor=MUTED, leading=13),
    'h2': style('h2', fontName='Serif-SemiBold', fontSize=15, leading=19),
    'h3': style('h3', fontName='Inter-SemiBold', fontSize=10, leading=14),
    'body': style('body'),
    'muted': style('muted', textColor=MUTED, fontSize=9, leading=13),
    'small': style('small', textColor=FAINT, fontSize=7.5, leading=10),
    'label': style('label', fontSize=8, leading=10, textColor=MUTED),
    'kpi': style('kpi', fontName='Serif-SemiBold', fontSize=15, leading=18),
    'kpi_big': style('kpi_big', fontName='Serif-SemiBold', fontSize=20, leading=23, textColor=BRASS),
    'right': style('right', alignment=2),
    'right_b': style('right_b', alignment=2, fontName='Inter-SemiBold'),
    'narrative': style('narrative', fontSize=9.5, leading=14.5),
    'narrative_h': style('narrative_h', fontName='Inter-SemiBold', fontSize=9.5, leading=14, textColor=BRASS, spaceBefore=4),
}


# --- Page decoration ---

class NumberedCanvas(canvas.Canvas):
    """Draws header/footer on every page once the total page count is known."""

    def __init__(self, *args, address: str = '', brand: str = 'SPREA', subtitle: str = 'Rapport de rénovation énergétique',
                 notice: str = '', **kwargs):
        super().__init__(*args, **kwargs)
        # Fixed line above the footer of every page
        self.notice = notice
        self._pages: List[dict] = []
        self.address = address
        self.brand = brand
        self.subtitle = subtitle

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._decorate(total)
            super().showPage()
        super().save()

    def _decorate(self, total: int):
        self.saveState()
        # Header band
        self.setFillColor(NAVY)
        self.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)
        self.setFillColor(BRASS_LIGHT)
        self.rect(0, PAGE_H - HEADER_H, PAGE_W, 1.2, fill=1, stroke=0)
        self.setFillColor(WHITE)
        self.setFont('Serif-SemiBold', 16)
        brand = self.brand if len(self.brand) <= 40 else self.brand[:39] + '…'
        self.drawString(MARGIN, PAGE_H - 1.18 * cm, brand)
        brand_w = pdfmetrics.stringWidth(brand, 'Serif-SemiBold', 16)
        self.setFont('Inter', 8)
        self.setFillColor(BRASS_LIGHT)
        self.drawString(MARGIN + brand_w + 0.4 * cm, PAGE_H - 1.15 * cm, self.subtitle)
        self.setFillColor(colors.HexColor('#97A1B3'))
        self.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.15 * cm, f"Établi le {date.today().strftime('%d/%m/%Y')}")
        # Footer
        self.setStrokeColor(LINE)
        self.setLineWidth(0.6)
        self.line(MARGIN, 1.35 * cm, PAGE_W - MARGIN, 1.35 * cm)
        self.setFont('Inter', 7.5)
        self.setFillColor(FAINT)
        address = self.address if len(self.address) < 90 else self.address[:87] + '…'
        self.drawString(MARGIN, 0.9 * cm, address)
        self.drawRightString(PAGE_W - MARGIN, 0.9 * cm, f"Page {self._pageNumber} / {total}")
        if self.notice:
            self.setFont('Inter', 7)
            self.drawString(MARGIN, 1.55 * cm, self.notice)
        self.restoreState()


def _paper(canv, doc):
    canv.saveState()
    canv.setFillColor(IVORY)
    canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canv.restoreState()


# --- Building blocks ---

def dpe_badge(label: Optional[str], size: float = 1.35 * cm, font_size: float = 20) -> Table:
    label = (label or '?').upper()
    bg, fg = DPE_COLORS.get(label, ('#CBD5E1', '#0A0F1A'))
    cell = Paragraph(label, style('badge', fontName='Inter-SemiBold', fontSize=font_size, leading=font_size + 2,
                                  alignment=1, textColor=colors.HexColor(fg)))
    t = Table([[cell]], colWidths=[size], rowHeights=[size])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg)),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    return t


def section(number: int, title: str) -> Table:
    t = Table([[Paragraph(str(number), style('n', fontName='Serif-SemiBold', fontSize=15, textColor=BRASS)),
                Paragraph(text(title), S['h2'])]], colWidths=[0.8 * cm, CONTENT_W - 0.8 * cm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.8, BRASS_LIGHT),
    ]))
    return t


def rows_table(rows: List[List[Any]], widths: List[float], bold_last: bool = False) -> Table:
    t = Table(rows, colWidths=widths)
    commands = [
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, LINE),
    ]
    if bold_last:
        commands.append(('LINEABOVE', (0, -1), (-1, -1), 0.9, INK))
    t.setStyle(TableStyle(commands))
    return t


def kv(label: str, value: str, value_style: str = 'right') -> List[Paragraph]:
    return [Paragraph(label, S['body']), Paragraph(value, S[value_style])]


def kpi_cell(label: str, value: str, big: bool = False) -> List[Paragraph]:
    return [Paragraph(text(label), S['label']), Spacer(1, 3), Paragraph(value, S['kpi_big'] if big else S['kpi'])]


def boxed(flowables: List[Any], background=WHITE, rule=None, padding: float = 12) -> Table:
    t = Table([[flowables]], colWidths=[CONTENT_W])
    commands = [
        ('BACKGROUND', (0, 0), (-1, -1), background),
        ('BOX', (0, 0), (-1, -1), 0.6, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), padding),
        ('RIGHTPADDING', (0, 0), (-1, -1), padding),
        ('TOPPADDING', (0, 0), (-1, -1), padding),
        ('BOTTOMPADDING', (0, 0), (-1, -1), padding),
    ]
    if rule is not None:
        commands.append(('LINEBEFORE', (0, 0), (0, -1), 2.5, rule))
    t.setStyle(TableStyle(commands))
    return t


def consistent_label(sim: Dict[str, Any], when: str = 'current') -> bool:
    """The official label is the worse of the energy and climate classes."""
    cep, ges, label = sim.get(f'{when}_cep_label'), sim.get(f'{when}_ges_label'), sim.get(f'{when}_label')
    return bool(cep and ges and label) and max(cep, ges) == label


def ges_note(sim: Dict[str, Any]) -> List[Any]:
    """The label is the worse of energy and climate: says so when the climate
    class, not the consumption shown on the scale, sets it."""
    notes = []
    for when, key, label, cep_label, ges in (("Aujourd'hui", 'current', sim.get('current_label'), sim.get('current_cep_label'), sim.get('initial_ges')),
                                             ("Après travaux", 'new', sim.get('new_label'), sim.get('new_cep_label'), sim.get('new_ges'))):
        if label and cep_label and label != cep_label and ges is not None and sim.get(f'{key}_ges_label') == label:
            notes.append(f"{when}, la consommation correspond à la classe {cep_label}, mais les émissions de gaz à effet "
                         f"de serre ({num(ges)}{NBSP}kg CO₂/m²/an) classent le logement en {label}")
    if not notes:
        return []
    return [Spacer(1, 3), Paragraph(" ; ".join(notes) + " : l'étiquette retient la moins bonne des deux classes.", S['small'])]


def dpe_scale(thresholds: List[Dict], current: str, target: str) -> List[Any]:
    rows = []
    n = len(thresholds)
    for i, t in enumerate(thresholds):
        bg, fg = DPE_COLORS[t['label']]
        prev = thresholds[i - 1]['max'] if i else None
        rng = f"≤ {t['max']}" if i == 0 else (f"> {prev}" if i == n - 1 else f"{prev + 1} à {t['max']}")
        width = (0.32 + i * 0.07) * (CONTENT_W - 4 * cm)
        bar = Table([[Paragraph(t['label'], style('sl', fontName='Inter-SemiBold', fontSize=10, textColor=colors.HexColor(fg))),
                      Paragraph(rng, style('sr', fontSize=7, alignment=2, textColor=colors.HexColor(fg)))]],
                    colWidths=[0.8 * cm, width - 0.8 * cm], rowHeights=[0.55 * cm])
        bar.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        marks = []
        if t['label'] == current:
            marks.append("Aujourd'hui")
        if t['label'] == target:
            marks.append('<font color="#A8853F"><b>Après travaux</b></font>')
        rows.append([bar, Paragraph(' · '.join(marks), S['muted'])])
    t = Table(rows, colWidths=[CONTENT_W - 4 * cm, 4 * cm])
    t.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (1, 0), (1, -1), 8),
    ]))
    return [t, Spacer(1, 3), Paragraph("Consommation en kWh/m²/an d'énergie primaire.", S['small'])]




def roi_label(roi: Optional[float]) -> str:
    if roi is None:
        return '–'
    if roi <= 0:
        return "immédiat (aucun reste à charge)"
    return "moins d'un an" if roi < 1 else f"environ {round(roi)}{NBSP}an{'s' if round(roi) > 1 else ''}"


def aid_amount(d: Dict[str, Any], value: float) -> str:
    """The aid, as a range when it follows the cost (rénovation d'ampleur), so
    that cost minus aid gives the rest to pay shown below it."""
    low, high = d.get('aids_low'), d.get('aids_high')
    if low is not None and high is not None and round(high / 100) != round(low / 100):
        return f"<font color='#3E8E63'>−{NBSP}{eur_r(low)} à {eur_r(high)}</font>"
    return f"<font color='#3E8E63'>−{NBSP}{eur_aid(value)}</font>"


def green_range(sim: Dict[str, Any]) -> str:
    """The 95 % range of the green value, unless so wide (few comparable
    sales) that it says nothing: "0 € à 134 000 €" for a value of 20 000 €."""
    if not green_range_shown(sim):
        return "fourchette large : peu de ventes comparables"
    return f"{eur_r(sim['latent_gain_low'], 500)} à {eur_r(sim['latent_gain_high'], 500)}"


def figures(report: Dict[str, Any]) -> Dict[str, int]:
    return display_figures(report['sim'], report['works'], report.get('extra_costs'))


def eur_span(low: float, high: float) -> str:
    return eur(low) if low == high else f"{eur(low)} à {eur(high)}"


def days(n: Any) -> str:
    n = int(n or 0)
    return f"{n} jour ouvré" if n <= 1 else f"{n} jours ouvrés"


def no_works_text(sim: Dict[str, Any]) -> str:
    """Why a report has no programme: a dwelling already efficient, or no
    work that improves it among those the simulation covers."""
    label = sim['current_label']
    if label in ('A', 'B'):
        return (f"Logement déjà performant (classe {label}) : pas de travaux nécessaires, ni pour louer, ni pour vendre. "
                "Des améliorations de confort restent possibles au cas par cas, sur devis.")
    if label == 'C':
        return ("Logement classé C : pas de travaux nécessaires pour louer ou pour vendre, sans limite de date. "
                "Des améliorations restent possibles au cas par cas, sur devis.")
    if label == 'D':
        return ("Logement classé D : il reste louable sans limite de date, et ce rapport ne retient pas de travaux. Pour viser "
                "C ou mieux, un programme peut être chiffré sur demande, ou établi par un audit énergétique.")
    return ("Aucun des travaux étudiés dans ce rapport n'améliore la classe de ce logement. Un audit énergétique réalisé "
            "sur place, avec un Accompagnateur Rénov', permet d'identifier les travaux adaptés.")


def eur_r(value: Optional[float], step: int = 100) -> str:
    """Estimates are shown rounded: 11 443 -> 11 400 €."""
    return eur(round((value or 0) / step) * step)


def eur_aid(value: Optional[float]) -> str:
    """Aids to the ten euros below 1 000 €, so that the total matches the
    amounts per work shown under it."""
    return eur_r(value, 10 if abs(value or 0) < 1000 else 100)


def eur_range(low: Optional[float], high: Optional[float]) -> str:
    if round((low or 0) / 100) == round((high or 0) / 100):
        return eur_r(low)
    return f"{eur_r(low)} à {eur_r(high)}"


def bullet_list(items: List[str], st: str = 'body') -> List[Any]:
    out = []
    for item in items:
        row = Table([[Paragraph('–', style('dash', textColor=BRASS)), Paragraph(text(item), S[st])]],
                    colWidths=[0.45 * cm, CONTENT_W - 0.45 * cm - 24])
        row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                 ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 1.5),
                                 ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5)]))
        out.append(row)
    return out


def share_bars(losses: List[Dict[str, Any]]) -> Table:
    bar_w = CONTENT_W * 0.45
    rows = []
    for item in losses:
        share = max(0.0, min(1.0, item['share']))
        filled = max(0.01, share) * bar_w
        bar = Table([['', '']], colWidths=[filled, bar_w - filled], rowHeights=[0.32 * cm])
        bar.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), BRASS_LIGHT), ('BACKGROUND', (1, 0), (1, 0), TINT),
                                 ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        rows.append([Paragraph(text(item['name']), S['body']), bar,
                     Paragraph(f"{round(share * 100)}{NBSP}%", S['right_b'])])
    t = Table(rows, colWidths=[CONTENT_W * 0.38, bar_w, CONTENT_W * 0.17])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                           ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 3),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    return t


def grid(rows: List[List[Any]], widths: List[float], header: bool = True, bold_last: bool = False) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, LINE),
    ]
    if header:
        commands.append(('LINEBELOW', (0, 0), (-1, 0), 0.9, INK))
    if bold_last:
        commands.append(('LINEABOVE', (0, -1), (-1, -1), 0.9, INK))
    t.setStyle(TableStyle(commands))
    return t


def head(label: str, align: int = 0) -> Paragraph:
    return Paragraph(label, style('th', fontName='Inter-SemiBold', fontSize=8, leading=10, textColor=MUTED, alignment=align))


ANALYSIS_TITLES = [
    ('diagnostic', 'Diagnostic'),
    ('strategie', 'Stratégie de travaux'),
    ('financement', 'Financement'),
]


# --- Report ---

# Investment file: one set of figures, three readers
INVESTMENT_TITLES = {"investisseur": "Dossier d'investissement", "acheteur": "Dossier acheteur", "proprietaire": "Dossier propriétaire"}
THESIS_HEADINGS = {
    "investisseur": {"these": "L'opportunité en bref", "risques": "Risques et vérifications avant offre",
                     "strategie": "Stratégie conseillée", "arguments": "Arguments de négociation"},
    "acheteur": {"these": "Le projet en bref", "risques": "Points à vérifier avec votre conseiller",
                 "strategie": "Le projet conseillé", "arguments": "Ce qui fait la valeur du projet"},
    "proprietaire": {"these": "Votre bien en bref", "risques": "Points que les acquéreurs vérifieront",
                     "strategie": "Notre recommandation", "arguments": "Comment le présenter aux acquéreurs"},
}
INVESTMENT_NOTICE = ("Estimations indicatives, à confirmer par devis d'artisans et diagnostics : "
                     "ni expertise immobilière, ni conseil en investissement.")


def comparables_table(market: Dict[str, Any], adjusted: bool) -> Table:
    """The closest comparable DVF sales. The median is computed on prices
    brought to the last quarter: they are shown next to the raw ones.
    Distance only when known (sales located by their street alone have none)."""
    with_distance = any(c.get('distance') is not None for c in market['comparables'])
    head_row = [head('Date'), head('Rue'), head('Surface', 2), head('Prix', 2),
                head('Prix /m² à la vente' if adjusted else 'Prix /m²', 2),
                *([head('Prix /m² actualisé', 2)] if adjusted else []), *([head('Distance', 2)] if with_distance else [])]
    comp_rows = [head_row]
    for c in market['comparables']:
        comp_rows.append([
            Paragraph(text(date.fromisoformat(c['date']).strftime('%m/%Y')) if c.get('date') else '–', S['body']),
            Paragraph(text(' · '.join(x for x in (c.get('street'), c.get('commune') if market.get('wide') else None) if x) or '–'), S['body']),
            Paragraph(f"{c['surface']:g}".replace('.', ',') + f"{NBSP}m²", S['right']),
            Paragraph(eur(c['price']), S['right']),
            Paragraph(eur(c['price_m2']), S['right']),
            *([Paragraph(eur(c.get('adjusted_m2') or c['price_m2']), S['right'])] if adjusted else []),
            *([Paragraph(distance_text(c.get('distance')), S['right'])] if with_distance else []),
        ])
    widths = [0.10, 0.27, 0.11, 0.13, 0.13, 0.13, 0.13] if adjusted else [0.12, 0.34, 0.13, 0.15, 0.13, 0.13]
    if not with_distance:
        # The street takes the room of the missing column
        widths = [widths[0], widths[1] + widths[-1], *widths[2:-1]]
    return grid(comp_rows, [CONTENT_W * w for w in widths])


class PDFReportGenerator:
    def _immeuble(self, report: Dict[str, Any], next_section) -> List[Any]:
        sheet = report.get('immeuble')
        if not sheet:
            return []
        copro, building, dims = sheet.get('copro'), sheet.get('building_dpe'), sheet['dimensions']
        rows = []
        if copro:
            lots = f"{copro['lots_main'] or '–'} lots principaux" + (f" dont {copro['lots_housing']} logements" if copro.get('lots_housing') else '')
            rows.append(kv('Copropriété', text(copro.get('name') or f"n° {copro['immat']}"), 'right_b'))
            rows.append(kv('Taille', text(lots), 'right'))
            syndic = copro.get('syndic_name') or (copro.get('syndic_type') or 'non renseigné').capitalize()
            rows.append(kv('Syndic', text(syndic), 'right'))
        if sheet.get('period'):
            rows.append(kv('Construction', text(sheet['period']), 'right'))
        if building:
            rows.append(kv("DPE de l'immeuble", text(f"Classe {building['label']} · {building['date_fr']}"), 'right_b'))
        apartments = sheet['apartments']
        if apartments['count'] > 1:
            dist = ', '.join(f"{n} en {l}" for l, n in apartments['distribution'].items() if n)
            rows.append(kv('DPE des appartements', text(f"{apartments['count']} publiés : {dist}"), 'right'))
        out: List[Any] = [CondPageBreak(8 * cm), Spacer(1, 18), next_section("L'immeuble et ses travaux à venir"), Spacer(1, 6)]
        if rows:
            out += [rows_table(rows, [CONTENT_W * 0.4, CONTENT_W * 0.6]), Spacer(1, 10)]
        if not copro:
            out += [Paragraph("Cette adresse n'a pas été retrouvée dans le registre national des copropriétés.", S['muted']), Spacer(1, 8)]
        if sheet.get('obligations'):
            out.append(Paragraph('Obligations de la copropriété', S['narrative_h']))
            items = []
            for o in sheet['obligations']:
                when = f" (depuis le {o['since'][8:10]}/{o['since'][5:7]}/{o['since'][:4]})" if o.get('since') and o['status'] != 'done' else ''
                items.append(f"{o['title']}{when} : {o['detail']}")
            out += [*bullet_list(items, 'muted'), Spacer(1, 8)]
        if not sheet.get('works') and sheet.get('works_note'):
            out += [Paragraph('Travaux collectifs', S['narrative_h']), Paragraph(text(sheet['works_note']), S['muted'])]
        if sheet.get('works'):
            source = "du DPE de l'immeuble" if sheet['works_source'] == 'immeuble' else "du DPE de l'appartement"
            table = [[head('Travaux collectifs probables'), head('Constat'), head('Immeuble', 2)]]
            for w in sheet['works']:
                table.append([Paragraph(text(w['name']), S['body']), Paragraph(text(w['reason']), S['muted']),
                              Paragraph(eur_range(w['low'], w['high']), S['right'])])
            table.append([Paragraph('<b>Total</b>', S['body']), Paragraph('', S['muted']),
                          Paragraph(eur_range(*sheet['total']), S['right_b'])])
            works_block: List[Any] = [Paragraph('Travaux collectifs à prévoir', S['narrative_h']), Spacer(1, 2),
                                      grid(table, [CONTENT_W * 0.38, CONTENT_W * 0.34, CONTENT_W * 0.28], bold_last=True)]
            est = sheet.get('estimate')
            if est:
                # The flat's share stays with the works table
                pct = str(round(est['share'] * 100, 1)).replace('.', ',')
                works_block += [Spacer(1, 8), boxed([
                    Paragraph(f"Quote-part de l'appartement (environ {pct}{NBSP}% de la surface) : "
                              f"<b>{eur_range(est['share_low'], est['share_high'])}</b>", S['body']),
                    Spacer(1, 2),
                    Paragraph(f"Après MaPrimeRénov' Copropriété ({round(est['aid_rates'][0] * 100)} à {round(est['aid_rates'][1] * 100)}{NBSP}% "
                              f"des travaux si le gain énergétique atteint 35{NBSP}%) : environ {eur_range(est['net_low'], est['net_high'])}.",
                              S['muted'])], rule=BRASS)]
            # The same walls or ventilation in the flat's programme and in the
            # collective works: say which comes first, not pay twice
            mine = {w['id'] for w in report.get('works', [])}
            theirs = {w['id'] for w in sheet['works']}
            overlap = []
            if mine & {'iti', 'ite'} and 'facade' in theirs:
                overlap.append("l'isolation des murs de l'appartement devient inutile si la copropriété vote l'isolation des façades")
            if 'vmc' in mine and 'vmc' in theirs:
                overlap.append("une ventilation individuelle fait double emploi avec une ventilation collective")
            if overlap:
                works_block += [Spacer(1, 6), Paragraph(
                    "À coordonner : " + " ; ".join(overlap) + ". Demandez au syndic si ces travaux sont prévus avant "
                    "d'engager les vôtres.", S['muted'])]
            out.append(KeepTogether(works_block))
            out += [Spacer(1, 6), Paragraph(
                f"Ordres de grandeur déduits {source} ({num(dims.get('surface'))}{NBSP}m² habitables{' estimés' if sheet['works_source'] != 'immeuble' else ''}, "
                f"{dims.get('levels')} niveau{'x' if (dims.get('levels') or 0) > 1 else ''}"
                + (f", {dims['dwellings']} logement{'s' if dims['dwellings'] > 1 else ''}" if dims.get('dwellings') else "")
                + "). Le montant réel dépend du plan pluriannuel "
                "de travaux voté en assemblée générale, et la répartition suit les tantièmes du règlement de copropriété. "
                "Sources : registre national des copropriétés (Anah), base DPE de l'ADEME.", S['small'])]
        return out

    def _rge(self, report: Dict[str, Any], next_section) -> List[Any]:
        rge = report.get('rge') or {}
        names = {w['id']: w['name'] for w in report.get('works', [])}
        groups = [(names.get(w, w), companies) for w, companies in (rge.get('works') or {}).items() if companies]
        if rge.get('global'):
            groups.append(('Rénovation globale (un seul interlocuteur)', rge['global']))
        if rge.get('audit'):
            groups.append(('Audit énergétique', rge['audit']))
        if not groups:
            return []
        out: List[Any] = [CondPageBreak(8 * cm), Spacer(1, 18), next_section('Des artisans RGE près du logement'), Spacer(1, 6),
                          Paragraph("Les aides de l'État ne sont versées que pour des travaux réalisés par une entreprise RGE. "
                                    "Voici les entreprises qualifiées les plus proches pour chaque travail, d'après l'annuaire public "
                                    "de l'ADEME, sans classement ni recommandation. Demandez plusieurs devis et vérifiez la "
                                    "qualification sur france-renov.gouv.fr.", S['muted']), Spacer(1, 8)]
        for title, companies in groups:
            rows = [[Paragraph(f"<b>{text(c['name'])}</b>", S['body']),
                     Paragraph(f"{text(c['city'])} · {str(c['distance_km']).replace('.', ',')}{NBSP}km", S['muted']),
                     Paragraph(text(' · '.join(x for x in (c.get('phone'), c.get('website')) if x) or '–'), S['muted'])]
                    for c in companies]
            block = [Paragraph(text(title), S['narrative_h']), Spacer(1, 2),
                     grid(rows, [CONTENT_W * 0.38, CONTENT_W * 0.24, CONTENT_W * 0.38], header=False), Spacer(1, 8)]
            out.append(KeepTogether(block))
        return out

    def generate(self, report: Dict[str, Any], analysis: Dict[str, Any], by_ai: bool = False) -> bytes:
        buffer = BytesIO()
        sim = report['sim']
        ident = report['identity']
        address = report['address']
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=HEADER_H + 1.0 * cm, bottomMargin=2.0 * cm,
            title=f"Rapport SPREA – {address['full']}", author='SPREA',
        )
        story: List[Any] = []
        story += self._title(report)
        story += self._summary(report, analysis)
        n = 0

        def next_section(title: str) -> Table:
            nonlocal n
            n += 1
            return section(n, title)

        # 1. Analysis
        # The AI notice only on a text Claude wrote, not on the rule-based one
        note = ("Analyse rédigée avec l'aide d'une intelligence artificielle (Claude, Anthropic) à partir des chiffres "
                "de ce rapport, à relire avec votre conseiller." if by_ai else
                "Analyse établie automatiquement à partir des chiffres de ce rapport, à relire avec votre conseiller.")
        block: List[Any] = [next_section('Notre analyse'), Spacer(1, 4), Paragraph(note, S['muted']), Spacer(1, 8)]
        for key, title in ANALYSIS_TITLES:
            block += [Paragraph(title, S['narrative_h']), Spacer(1, 2), Paragraph(text(analysis[key]), S['narrative']), Spacer(1, 6)]
        block += [Paragraph('Pour un bailleur' if report['is_investor'] else 'Pour vous, propriétaire occupant', S['narrative_h']),
                  Spacer(1, 2), Paragraph(text(analysis['profil']), S['narrative']), Spacer(1, 6),
                  Paragraph('Points de vigilance', S['narrative_h']), Spacer(1, 3), *bullet_list(analysis['vigilance'])]
        story += [Spacer(1, 18), *block]

        # 2. Today
        story += [CondPageBreak(9 * cm), Spacer(1, 18), next_section("Le logement aujourd'hui"), Spacer(1, 8)]
        story += self._today(report)

        # 3. Works
        story += [CondPageBreak(9 * cm), Spacer(1, 18), next_section('Le programme de travaux'), Spacer(1, 8)]
        story += self._works(report)

        # 4. Financing and 5. value: nothing to finance nor to value without works
        if report['works']:
            story += [CondPageBreak(9 * cm), Spacer(1, 18), next_section('Le plan de financement'), Spacer(1, 8)]
            story += self._financing(report)
            story += [CondPageBreak(6 * cm), Spacer(1, 18),
                      next_section('Valeur et rentabilité locative' if report['is_investor'] else 'Valeur du bien'), Spacer(1, 8)]
            story += self._value(report)

        # Building of an apartment in a copropriété
        story += self._immeuble(report, next_section)

        # 6. Steps
        steps: List[Any] = [next_section('Calendrier et prochaines étapes'), Spacer(1, 8)] if report['works'] else []
        for i, step in enumerate(report['steps'] if report['works'] else [], 1):
            row = Table([[Paragraph(str(i), style('ns', fontName='Serif-SemiBold', fontSize=12, textColor=BRASS)),
                          [Paragraph(f"<b>{text(step['title'])}</b> <font color='#A8853F' size='8'>{text(step['when'])}</font>", S['body']),
                           Paragraph(text(step['text']), S['muted'])]]],
                        colWidths=[0.8 * cm, CONTENT_W - 0.8 * cm])
            row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                     ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
            steps.append(row)
        if report['works']:
            story += [CondPageBreak(8 * cm), Spacer(1, 18), *steps]

        # Qualified companies near the dwelling
        story += self._rge(report, next_section)

        # 7. Method
        method = [next_section('Méthode et hypothèses'), Spacer(1, 8), *bullet_list(report['assumptions'], 'muted'), Spacer(1, 10),
                  Paragraph(
                      "Simulation indicative fondée sur les données publiques de l'ADEME et des coûts moyens de marché. "
                      "Ce document ne constitue ni un DPE, ni un audit énergétique réglementaire, ni un devis. "
                      f"Les montants d'aides ({text(sim['aid_rules'])}) doivent être confirmés par France Rénov' "
                      "ou un Accompagnateur Rénov' avant tout engagement.", S['small'])]
        story += [CondPageBreak(6 * cm), Spacer(1, 18), KeepTogether(method)]

        doc.build(story, onFirstPage=_paper, onLaterPages=_paper,
                  canvasmaker=lambda *a, **k: NumberedCanvas(*a, address=address['full'], **k))
        return buffer.getvalue()

    # --- Parts ---

    def _title(self, report: Dict[str, Any]) -> List[Any]:
        ident = report['identity']
        address = report['address']
        meta = ' · '.join(x for x in [
            text(ident['building_type']),
            f"{ident['surface']:g}".replace('.', ',') + f"{NBSP}m²" if ident.get('surface') else '',
            text(ident['period']) if ident.get('period') else '',
            ("rez-de-chaussée" if str(ident['floor']) == "0" else f"étage {text(ident['floor'])}") if ident.get('floor') else '',
        ] if x)
        dpe_ref = ' · '.join(x for x in [
            f"DPE du {text(ident['dpe_date'])}" if ident.get('dpe_date') else 'DPE',
            f"n° {text(ident['dpe_number'])}" if ident.get('dpe_number') else '',
        ] if x)
        out: List[Any] = [Paragraph(text(address['street']), S['address'])]
        if address['locality']:
            out.append(Paragraph(text(address['locality']), style('loc', fontName='Serif', fontSize=13, leading=17, textColor=MUTED)))
        out += [Spacer(1, 4), Paragraph(meta, S['meta']), Paragraph(dpe_ref, style('ref', fontSize=8, textColor=FAINT)), Spacer(1, 16)]
        return out

    def _summary(self, report: Dict[str, Any], analysis: Dict[str, Any]) -> List[Any]:
        sim = report['sim']
        gain = sim['gain_classes']
        labels = Table([[
            dpe_badge(sim['current_label']),
            Paragraph('→', style('arrow', fontSize=18, alignment=1, textColor=FAINT, leading=20)),
            dpe_badge(sim['new_label']),
            [Paragraph(f"<b>{'+' + str(gain) + ' classe' + ('s' if gain > 1 else '') if gain else 'Pas de changement de classe'}</b>", S['body']),
             Paragraph(f"{num(sim['initial_cep'])} → {num(sim['new_cep'])}{NBSP}kWh/m²/an", S['muted'])],
        ]], colWidths=[1.6 * cm, 1.0 * cm, 1.6 * cm, CONTENT_W - 4.2 * cm - 24])
        labels.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))

        fig = figures(report)
        aids = fig['aids']
        small = style('kpi_small', fontSize=7.5, leading=10, textColor=MUTED)
        kpi_w = (CONTENT_W - 24) / 4
        kpis = Table([[
            [*kpi_cell('Coût des travaux', f"≈{NBSP}{eur(fig['cost'])}"),
             Paragraph(f"entre {eur(fig['cost_low'])} et {eur(fig['cost_high'])}", small)],
            [*kpi_cell('Aides estimées', f"<font color='#3E8E63'>−{NBSP}{eur(aids)}</font>"),
             *([Paragraph(f"entre {eur(fig['aids_low'])} et {eur(fig['aids_high'])}", small)]
               if fig['aids_low'] != fig['aids_high'] else [])],
            [*kpi_cell('Reste à charge', f"≈{NBSP}{eur(fig['rest'])}", big=True),
             Paragraph(f"entre {eur(fig['rest_low'])} et {eur(fig['rest_high'])}", small)],
            kpi_cell("Économies d'énergie", f"<font color='#3E8E63'>{eur_r(sim['annual_savings'], 10)}</font>"
                                             f"<font size='9' color='#5B6577'> / an</font>"),
        ]], colWidths=[kpi_w] * 4)
        kpis.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (2, 0), (2, 0), TINT),
            ('LINEAFTER', (0, 0), (1, 0), 0.5, LINE),
        ]))

        if not report['works']:
            kpis = Paragraph(no_works_text(sim), S['body'])
        roi_text = roi_label(sim['roi_years'])
        # Below 250 €: no measurable gap between the two classes, not "+0 €"
        measurable = round((sim['latent_gain'] or 0) / 500) > 0
        green = (f"+{NBSP}{eur_r(sim['latent_gain'], 500)} <font size='7.5' color='#8A93A3'>"
                 f"({green_range(sim)})</font>") if measurable else \
            ("Pas d'écart de prix mesuré" if sim['new_label'] != sim['current_label'] else '–')
        after_color = '#3E8E63' if sim['new_ban_date'] is None else '#C4553A'
        rows = [
            kv('Retour sur investissement', roi_text),
            kv('Valeur verte du bien', green),
            kv('Location aujourd\'hui', text(sim['rental_status'])),
            kv('Location après travaux', f"<font color='{after_color}'>{text(sim['new_rental_status'])}</font>"),
        ]
        if not report['works']:
            rows = [rows[2]]
        elif report['price_is_default']:
            rows = [rows[0]] + rows[2:]
        secondary = rows_table(rows, [CONTENT_W * 0.5 - 24, CONTENT_W * 0.5])

        verdict = boxed([Paragraph("L'essentiel", S['narrative_h']), Spacer(1, 2), Paragraph(text(analysis['verdict']), S['narrative'])],
                        rule=BRASS_LIGHT, padding=10)
        return [KeepTogether([
            Paragraph('Synthèse', S['h2']),
            Spacer(1, 8),
            boxed([labels, Spacer(1, 12), kpis, Spacer(1, 8), secondary]),
            Spacer(1, 10),
            verdict,
        ])]

    def _today(self, report: Dict[str, Any]) -> List[Any]:
        sim = report['sim']
        ident = report['identity']
        rows = [
            # Sub-classes only when they explain the official label (recomputed
            # thresholds can differ from the diagnostician's)
            kv('Étiquette DPE (énergie / climat)' if consistent_label(sim) else 'Étiquette DPE',
               f"<b>{text(sim['current_label'])}</b>"
               + (f" <font color='#5B6577'>({text(sim['current_cep_label'])} / {text(sim['current_ges_label'])})</font>"
                  if consistent_label(sim) else '')),
            kv("Consommation d'énergie primaire", f"{num(sim['initial_cep'])}{NBSP}kWh/m²/an"),
            kv('Émissions de gaz à effet de serre', f"{num(sim['initial_ges'])}{NBSP}kg CO₂/m²/an"),
        ]
        for label, key in (('Chauffage', 'heating'), ('Eau chaude', 'hot_water'), ('Ventilation', 'ventilation')):
            if ident.get(key):
                rows.append(kv(label, text(ident[key])))
        for item in report.get('insulation_state') or []:
            rows.append(kv(text(item['label']), text(item['value'])))
        rows.append(kv("Facture d'énergie estimée", f"{eur_r(sim['annual_bill_before'], 10)} / an"))
        if ident.get('dpe_annual_cost'):
            rows.append(kv('Coût annuel indiqué par le DPE (prix 2021)', f"{eur(float(ident['dpe_annual_cost']))} / an"))
        out: List[Any] = [rows_table(rows, [CONTENT_W * 0.5, CONTENT_W * 0.5])]

        out += [Spacer(1, 14), KeepTogether([
            Paragraph('Où part la chaleur', S['h3']), Spacer(1, 2),
            Paragraph('Répartition des pertes de chaleur du logement, calculée à partir de son DPE.', S['muted']), Spacer(1, 6),
            share_bars(report['losses']),
        ])]

        usage_rows = [[head('Usage'), head("Aujourd'hui", 2), head('Après travaux', 2)]]
        for u in report['usages']:
            if u['usage'] == 'hot_water' and not u['eur_before'] and not u['eur_after']:
                # No hot water consumption in the DPE: said as such, not "0 €"
                usage_rows.append([Paragraph(text(u['name']), S['body']),
                                   Paragraph("<font color='#8A93A3'>non renseignée dans le DPE</font>", S['right']),
                                   Paragraph("<font color='#8A93A3'>–</font>", S['right'])])
                continue
            after = eur_r(u['eur_after'], 10)
            if u['energy_after'] != u['energy_before']:
                after += f" <font size='7.5' color='#8A93A3'>({text(u['energy_after'])})</font>"
            usage_rows.append([Paragraph(text(u['name']), S['body']), Paragraph(eur_r(u['eur_before'], 10), S['right']),
                               Paragraph(after, S['right'])])
        usage_rows.append([Paragraph('<b>Total par an</b>', S['body']),
                           Paragraph(f"<b>{eur(sum(r(u['eur_before'], 10) for u in report['usages']))}</b>", S['right']),
                           Paragraph(f"<font color='#3E8E63'><b>{eur(sum(r(u['eur_after'], 10) for u in report['usages']))}</b></font>", S['right'])])
        widths = [CONTENT_W * 0.5, CONTENT_W * 0.25, CONTENT_W * 0.25]
        if not report['works']:
            # Nothing changes without works: no "after" column
            usage_rows = [row[:2] for row in usage_rows]
            usage_rows[0][1] = head('Par an', 2)
            widths = [CONTENT_W * 0.6, CONTENT_W * 0.4]
        out += [Spacer(1, 14), KeepTogether([
            Paragraph('Votre facture par usage', S['h3']), Spacer(1, 6),
            grid(usage_rows, widths, bold_last=True),
            Spacer(1, 3), Paragraph("Énergie facturée aux prix moyens actuels, hors abonnement.", S['small']),
        ])]

        reg = report['regulatory']
        calendar = ' · '.join(f"{label} : {d}" for label, d in reg['calendar'])
        out += [Spacer(1, 14), KeepTogether([
            Paragraph('Cadre réglementaire', S['h3']), Spacer(1, 6),
            rows_table([kv(text(i['label']), text(i['value'])) for i in reg['items']], [CONTENT_W * 0.32, CONTENT_W * 0.68]),
            Spacer(1, 3),
            Paragraph(f"Calendrier d'interdiction de louer (Loi Climat et Résilience), par classe : {text(calendar)}. "
                      "Il s'applique aux nouveaux baux et aux renouvellements."
                      + (" Depuis le 01/01/2023, les logements qui consomment plus de 450 kWh/m²/an d'énergie finale sont "
                         "déjà interdits à la location." if reg.get('ban_2023') else ''), S['small']),
        ])]
        return out

    def _works(self, report: Dict[str, Any]) -> List[Any]:
        sim = report['sim']
        works = report['works']
        if not works:
            return [Paragraph(no_works_text(sim), S['body'])]
        out: List[Any] = [Paragraph(
            "Dans l'ordre conseillé : l'enveloppe d'abord (toiture, murs, plancher, fenêtres), puis la ventilation, puis les "
            "équipements, qui peuvent alors être dimensionnés sur des besoins réduits. « Effet seul » : ce que le geste apporterait "
            "réalisé sans les autres ; les effets ne s'additionnent pas exactement.", S['muted']), Spacer(1, 8)]
        rows = [[head('Travaux'), head('Fourchette TTC', 2)]]
        for i, w in enumerate(works, 1):
            name = f"<b>{i}. {text(w['name'])}</b>"
            if w['suggested']:
                name += " <font size='7' color='#A8853F'>RECOMMANDÉ</font>"
            effect = []
            if w['cep_saved'] >= 1:
                effect.append(f"−{NBSP}{num(w['cep_saved'])}{NBSP}kWh/m²/an")
            if w['bill_saving'] >= 5:
                effect.append(f"−{NBSP}{eur_r(w['bill_saving'], 10)}/an sur la facture")
            cell = [Paragraph(name, S['body'])]
            if w['reason']:
                cell.append(Paragraph(text(w['reason']), S['muted']))
            if effect:
                cell.append(Paragraph('Effet seul : ' + ' · '.join(effect), style('eff', fontSize=8.5, leading=12, textColor=SAGE)))
            if w.get('spec'):
                cell.append(Paragraph('<b>Préconisation :</b> ' + text(w['spec']), style('spec', fontSize=8.5, leading=12, textColor=INK)))
            if w['caution']:
                cell.append(Paragraph('À prévoir : ' + text(w['caution']), style('caut', fontSize=8.5, leading=12, textColor=CORAL)))
            rows.append([cell, Paragraph(eur_range(w['cost_low'], w['cost_high']), S['right'])])
        for extra in report['extra_costs']:
            rows.append([Paragraph(text(extra['name']), S['body']), Paragraph(eur_r(extra['cost'], 10), S['right'])])
        rows.append([Paragraph('<b>Total des travaux TTC</b>', S['body']),
                     Paragraph(f"<b>{eur_span(figures(report)['cost_low'], figures(report)['cost_high'])}</b>", S['right'])])
        table = grid(rows, [CONTENT_W * 0.7, CONTENT_W * 0.3], bold_last=True)
        table.setStyle(TableStyle([('VALIGN', (0, 1), (-1, -2), 'TOP')]))
        out.append(table)
        notes = []
        if sim.get('duration_days'):
            notes.append(f"Durée indicative du chantier : {days(sim['duration_days'])}, hors délais d'approvisionnement.")
        notes.append("TVA à 5,5 % incluse. Fourchettes fondées sur les prix moyens du marché : seuls des devis fixent le prix réel.")
        if sim.get('new_ban_date'):
            notes.append(f"Attention : après ces travaux, le logement reste concerné par l'interdiction de louer "
                         f"({text(sim['new_rental_status']).lower()}) ; "
                         + ("viser une classe de plus le met à l'abri plus longtemps." if report.get('better_label_reachable') else
                            "aucun des autres travaux étudiés ne permet de gagner une classe de plus : un audit énergétique "
                            "sur place peut identifier d'autres leviers."))
        out += [Spacer(1, 6), Paragraph(' '.join(notes), S['muted'])]

        alt = report.get('wall_alternative')
        if alt:
            exterior = alt['work'] == 'ite'
            diff = alt['rest_difference']
            rows_alt = [
                kv(f"{text(alt['work_name'])}", eur_range(alt['work_cost_low'], alt['work_cost_high'])),
                kv('Coût total du programme', eur_range(alt['cost_low'], alt['cost_high'])),
                kv('Aides estimées', aid_amount(alt, alt['aids'])),
                kv('<b>Reste à charge</b>', f"<font color='#A8853F'><b>{eur_range(alt['rest_to_pay_low'], alt['rest_to_pay_high'])}</b></font>"),
            ]
            pros = ("Aucune perte de surface habitable, ponts thermiques traités, chantier sans libérer les pièces, façade "
                    "rénovée. En contrepartie : coût plus élevé et déclaration préalable en mairie." if exterior else
                    "Moins cher et sans formalité en mairie. En contrepartie : perte de surface habitable, ponts thermiques "
                    "en partie conservés, pièces à libérer pendant le chantier.")
            out += [Spacer(1, 12), KeepTogether([boxed([
                Paragraph(f"<b>Autre solution pour les murs : {text(alt['work_name'][0].lower() + alt['work_name'][1:])}</b>", S['body']),
                Spacer(1, 3),
                Paragraph(f"{pros} Résultat : classe {text(alt['new_label'])}, facture d'environ "
                          f"{eur_r(alt['annual_bill_after'], 10)} par an, reste à charge "
                          f"{'supérieur' if diff > 0 else 'inférieur'} d'environ {eur_r(abs(diff))}."
                          + (f" À noter : {text(alt['caution'])}." if alt.get('caution') else ''), S['muted']),
                Spacer(1, 6), rows_table(rows_alt, [CONTENT_W * 0.55, CONTENT_W * 0.35], bold_last=True),
            ], background=TINT, rule=BRASS_LIGHT, padding=9)])]

        if sim.get('thresholds'):
            out += [Spacer(1, 14), KeepTogether([
                Paragraph("Effet sur l'étiquette énergie", S['h3']), Spacer(1, 6),
                *dpe_scale(sim['thresholds'], sim['current_label'], sim['new_label']),
                *ges_note(sim),
                Spacer(1, 6),
                Paragraph(f"Facture d'énergie estimée : {eur_r(sim['annual_bill_before'], 10)} → "
                          f"<font color='#3E8E63'><b>{eur_r(sim['annual_bill_after'], 10)}</b></font> par an.", S['body']),
            ])]
        return out

    def _financing(self, report: Dict[str, Any]) -> List[Any]:
        sim = report['sim']
        fin = report['financing']
        pathway = sim['aid_pathway']
        fig = figures(report)
        rows = [kv('Coût des travaux', eur_span(fig['cost_low'], fig['cost_high']))]
        if pathway == 'accompagne':
            rows.append(kv("MaPrimeRénov' rénovation d'ampleur",
                           f"<font color='#3E8E63'>−{NBSP}{eur_span(fig['aids_low'], fig['aids_high'])}</font>"))
        else:
            if fig['mpr']:
                rows.append(kv("MaPrimeRénov' par geste", f"<font color='#3E8E63'>−{NBSP}{eur(fig['mpr'])}</font>"))
            if fig['cee']:
                rows.append(kv('Primes CEE (estimation)', f"<font color='#3E8E63'>−{NBSP}{eur(fig['cee'])}</font>"))
            if not fig['mpr'] and not fig['cee']:
                rows.append(kv('Aides', '–'))
        rows.append(kv('<b>Reste à charge</b>', f"<font color='#A8853F'><b>{eur_span(fig['rest_low'], fig['rest_high'])}</b></font>"))
        out: List[Any] = [rows_table(rows, [CONTENT_W * 0.6, CONTENT_W * 0.4], bold_last=True)]

        per_work = [w for w in report['works'] if w['aid']]
        if pathway == 'geste' and per_work:
            detail = [[head('Aides par travaux'), head('Montant estimé', 2)]]
            detail += [[Paragraph(text(w['name']), S['body']), Paragraph(eur_r(w['aid'], 10), S['right'])] for w in per_work]
            out += [Spacer(1, 10), grid(detail, [CONTENT_W * 0.6, CONTENT_W * 0.4])]

        notes = [f"Catégorie de revenus retenue : {text(sim['income_profile'])}."]
        notes += [text(n) for n in sim.get('aid_notes') or []]
        out += [Spacer(1, 6)] + [Paragraph(n, S['muted']) for n in notes]

        if sim.get('aid_blockers') and fin['ampleur_possible_label']:
            out += [Spacer(1, 10), boxed([Paragraph("<b>Pourquoi pas la rénovation d'ampleur ?</b>", S['body']), Spacer(1, 3),
                                          *bullet_list(sim['aid_blockers'], 'muted')],
                                         background=TINT, rule=BRASS_LIGHT, padding=9)]

        variant = report.get('ampleur_variant')
        if variant:
            vrows = [
                kv(f"+ {text(variant['work_name'])}", eur_range(variant['work_cost_low'], variant['work_cost_high'])),
                kv("Coût total des travaux", eur_range(variant['cost_low'], variant['cost_high'])),
                kv("MaPrimeRénov' rénovation d'ampleur", aid_amount(variant, variant['subsidies'])),
                kv('<b>Reste à charge</b>', f"<font color='#A8853F'><b>{eur_range(variant['rest_to_pay_low'], variant['rest_to_pay_high'])}</b></font>"),
            ]
            gain = (f"Pour environ {eur_r(variant['saving_vs_programme'])} de moins à votre charge, le logement est mieux isolé "
                    f"(classe {variant['new_label']}, facture d'environ {eur_r(variant['annual_bill_after'], 10)} par an).")
            out += [Spacer(1, 12), KeepTogether([boxed([
                Paragraph(f"<b>Variante : ajouter {text(variant['work_phrase'])} "
                          "ouvre la rénovation d'ampleur</b>", S['body']), Spacer(1, 3),
                Paragraph("Avec un deuxième travail d'isolation, le programme devient éligible à MaPrimeRénov' rénovation "
                          "d'ampleur, qui finance une part de l'ensemble des travaux. " + gain, S['muted']), Spacer(1, 6),
                rows_table(vrows, [CONTENT_W * 0.55, CONTENT_W * 0.35], bold_last=True), Spacer(1, 4),
                *([Paragraph(f"<b>À vérifier :</b> {text(variant['check'])}", S['small']), Spacer(1, 2)] if variant.get('check') else []),
                Paragraph("Conditions : accompagnement obligatoire par un Accompagnateur Rénov' (en partie pris en charge par l'Anah) "
                          "et audit énergétique confirmant un gain d'au moins deux classes. Primes CEE non cumulables.", S['small']),
            ], background=TINT, rule=BRASS_LIGHT, padding=9)])]

        if sim['eco_ptz_amount']:
            loan = [
                kv('Éco-prêt à taux zéro', eur(figures(report)['eco_ptz'])),
                kv('Durée', f"{fin['eco_ptz_years']}{NBSP}ans"),
                kv('Mensualité', f"{eur(fin['eco_ptz_monthly'])} / mois"),
                kv('Économie sur la facture', f"<font color='#3E8E63'>−{NBSP}{eur(fin['monthly_saving'])} / mois</font>"),
            ]
            # From the two rounded amounts shown above it
            effort = round(fin['eco_ptz_monthly']) - round(fin['monthly_saving'])
            loan.append(kv('<b>Effort mensuel net</b>', f"<b>{eur(effort)} / mois</b>" if effort > 0
                           else "<font color='#3E8E63'><b>Les économies couvrent la mensualité</b></font>"))
            out += [Spacer(1, 14), KeepTogether([
                Paragraph('Financer le reste à charge', S['h3']), Spacer(1, 6),
                rows_table(loan, [CONTENT_W * 0.6, CONTENT_W * 0.4], bold_last=True),
                Spacer(1, 3),
                Paragraph("Sans intérêts ni frais de dossier, sous conditions de la banque. "
                          + ("Il se cumule avec MaPrimeRénov'." if sim['subsidies'] > 0 else "Il se cumule avec les primes CEE." if sim['cee_est'] > 0 else ""), S['small']),
            ])]
        return out

    def _value(self, report: Dict[str, Any]) -> List[Any]:
        sim = report['sim']
        rows = [kv('Retour sur investissement', roi_label(sim['roi_years']))]
        if report['price_is_default']:
            # Without local sales, a national default price would invent a value
            rows.append(kv('Valeur verte estimée', 'Non estimée : pas de ventes connues à proximité'))
        elif round((sim['latent_gain'] or 0) / 500) > 0:
            rows += [
                kv('Prix de marché local', f"{eur(report['price_per_m2'])}/m²" + (" <font size='7.5' color='#8A93A3'>(par défaut)</font>" if report['price_is_default'] else '')),
                kv('Valeur verte estimée', f"<b>+{NBSP}{eur_r(sim['latent_gain'], 500)}</b>"),
                kv('Fourchette', green_range(sim)),
            ]
        elif sim['new_label'] != sim['current_label']:
            rows.append(kv('Valeur verte estimée', "Pas d'écart de prix mesuré entre ces classes"))
        else:
            rows.append(kv('Valeur verte estimée', '–'))
        notes = []
        if report.get('price_source') and not report['price_is_default']:
            notes.append(f"Prix local : {text(report['price_source'])}.")
        if sim.get('green_value_basis') and not report['price_is_default']:
            notes.append(f"Valeur verte : {text(sim['green_value_basis'])}.")
            if sim['green_value_method'] in ('department', 'national'):
                notes.append("Les ventes ont été rapprochées une à une du DPE du logement vendu ; l'écart est mesuré à emplacement, "
                             "surface, époque de construction et date de vente comparables. Fourchette : de la moitié du bas de l'intervalle "
                             "de confiance à 95 % de l'écart à la totalité de son haut.")
        out: List[Any] = [rows_table(rows, [CONTENT_W * 0.6, CONTENT_W * 0.4]), Spacer(1, 4)] + [Paragraph(n, S['small']) for n in notes]
        if report['is_investor']:
            inv_w = CONTENT_W / 4
            inv = Table([[
                kpi_cell('Rendement brut', f"{sim['yield_brut']:.1f}".replace('.', ',') + f"{NBSP}%"),
                kpi_cell('Trésorerie mensuelle', eur(sim['cashflow'])),
                kpi_cell("Économie d'impôt", eur_r(sim['tax_benefit'])),
                kpi_cell('Coût net après impôt', eur_r(sim['net_investor_cost'])),
            ]], colWidths=[inv_w] * 4)
            inv.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                     ('LINEAFTER', (0, 0), (2, 0), 0.5, LINE), ('LEFTPADDING', (1, 0), (-1, 0), 8)]))
            out += [Spacer(1, 12), inv, Spacer(1, 6), Paragraph(
                f"Prix d'achat {eur(report['purchase_price'])}, loyer {eur(report['monthly_rent'])} par mois. Trésorerie : loyer moins la "
                "mensualité de l'éco-PTZ, et d'un prêt bancaire (7 ans, 4,5 %) pour la part qu'il ne couvre pas, hors charges et impôts. Économie d'impôt : "
                "déduction des travaux des revenus fonciers au taux marginal saisi.", S['muted'])]
        return out


    # --- Avis de valeur (Pro, agency branding) ---

    def generate_valuation(self, v: Dict[str, Any]) -> bytes:
        buffer = BytesIO()
        agency = v['agency']
        address = v['address']
        market = v['market']
        prop = v['property']
        meta = v.get('meta') or {}
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                                topMargin=HEADER_H + 1.0 * cm, bottomMargin=2.0 * cm,
                                title=f"Avis de valeur – {address['full']}", author=agency.get('agency_name') or 'SPREA')
        story: List[Any] = [Paragraph('Avis de valeur', style('kicker', fontSize=9, textColor=BRASS)),
                            Paragraph(text(address['street']), S['address'])]
        if address['locality']:
            story.append(Paragraph(text(address['locality']), style('loc', fontName='Serif', fontSize=13, leading=17, textColor=MUTED)))
        facts = ' · '.join(x for x in [
            text((prop.get('building_type') or 'Logement').capitalize()),
            f"{prop['surface']:g}".replace('.', ',') + f"{NBSP}m²",
            text(meta.get('construction_period') or prop.get('construction_period') or ''),
            f"DPE {text(v['current_label'])}" + (f" (n° {text(meta['ademe_dpe_number'])})" if meta.get('ademe_dpe_number') else ''),
        ] if x)
        story += [Spacer(1, 4), Paragraph(facts, S['meta'])]
        if v.get('client_name'):
            story.append(Paragraph(f"Établi pour {text(v['client_name'])}", S['meta']))
        story.append(Spacer(1, 14))

        # Synthesis
        now, after = v['value_now'], v['value_after']
        w = (CONTENT_W - 24) / (3 if after else 1)
        cells = [[*kpi_cell(f"Valeur actuelle (classe {v['current_label']})", f"≈{NBSP}{eur(now['value'])}", big=True),
                  Paragraph(f"entre {eur(now['low'])} et {eur(now['high'])}", style('ks', fontSize=7.5, leading=10, textColor=MUTED))]]
        if after:
            cells += [
                [*kpi_cell(f"Après rénovation (classe {v['target_label']})", f"≈{NBSP}{eur(after['value'])}"),
                 Paragraph(f"entre {eur(after['low'])} et {eur(after['high'])}", style('ks2', fontSize=7.5, leading=10, textColor=MUTED))],
                [*kpi_cell('Plus-value nette des travaux' if (v['net_gain'] or 0) >= 0 else 'Bilan net des travaux', f"<font color='{'#3E8E63' if (v['net_gain'] or 0) >= 0 else '#C4553A'}'>"
                                                          f"{'+' if (v['net_gain'] or 0) >= 0 else '−'}{NBSP}{eur(abs(v['net_gain'] or 0))}</font>"),
                 Paragraph("valeur gagnée moins le reste à charge", style('ks3', fontSize=7.5, leading=10, textColor=MUTED))],
            ]
        kpis = Table([cells], colWidths=[w] * len(cells))
        kpis.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8),
                                  ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                                  ('BACKGROUND', (0, 0), (0, 0), TINT), ('LINEAFTER', (0, 0), (-2, 0), 0.5, LINE)]))
        story += [Paragraph('Synthèse', S['h2']), Spacer(1, 8), boxed([kpis])]
        if v.get('adjustment_pct'):
            note = f" : {text(v['adjustment_note'])}" if v.get('adjustment_note') else ''
            story += [Spacer(1, 4), Paragraph(f"Ajustement du conseiller : {v['adjustment_pct']:+.0f}{NBSP}%{note}.", S['muted'])]

        n = 0

        def next_section(title: str) -> Table:
            nonlocal n
            n += 1
            return section(n, title)

        # Local market
        # Markets saved before these flags: read them from the source text
        surface_matched = market.get('surface_matched', 'surface comparable' in (market.get('source') or ''))
        adjusted = market.get('adjusted', 'actualisées' in (market.get('source') or ''))
        similar = " et de surface comparable" if surface_matched else ""
        rows = [
            kv('Prix médian au m² des ventes comparables', f"<b>{eur(market['price_per_m2'])}</b>"),
            kv('Moitié des ventes entre', f"{eur(market['q25'])} et {eur(market['q75'])} /m²"),
            kv('Ventes retenues', f"{num(market['sales'])} ventes {text(market['scope'])} ({text(market['period'])})"),
            kv(f"Prix au m² pour ce bien (classe {v['current_label']})", f"<b>{eur(v['price_m2_now'])}</b>"),
        ]
        story += [CondPageBreak(7 * cm), Spacer(1, 18), next_section('Le marché local'), Spacer(1, 8),
                  rows_table(rows, [CONTENT_W * 0.55, CONTENT_W * 0.45]), Spacer(1, 3),
                  Paragraph(f"Source : {text(market['source'])}. Ventes d'un seul logement du même type{similar} "
                            "(données DVF, DGFiP), hors ventes atypiques.", S['small'])]
        if market.get('comparables'):
            story += [Spacer(1, 10), Paragraph('Ventes comparables les plus proches', S['h3']), Spacer(1, 4),
                      comparables_table(market, adjusted)]

        # DPE effect
        if v.get('class_premium'):
            prem = v['class_premium']
            cls_rows = [[head('Classe DPE'), *[head(c, 1) for c in LABELS]],
                        [Paragraph("Écart de prix vs D", S['body']),
                         *[Paragraph(("<b>" if c in (v['current_label'], v['target_label']) else '') + f"{prem[c]:+.0f}{NBSP}%".replace('+0', '0')
                                     + ("</b>" if c in (v['current_label'], v['target_label']) else ''), style(f'p{c}', alignment=1)) for c in LABELS]]]
            scope = 'du département' if v.get('class_scope') == 'department' else 'nationales'
            story += [CondPageBreak(5 * cm), Spacer(1, 18), next_section("L'effet du DPE sur le prix"), Spacer(1, 8),
                      grid(cls_rows, [CONTENT_W * 0.30] + [CONTENT_W * 0.10] * 7), Spacer(1, 3),
                      Paragraph(f"Écarts mesurés sur {format(v.get('class_sample') or 0, ',').replace(',', NBSP)} ventes {scope} rapprochées "
                                "une à une du DPE du logement vendu, à emplacement, surface, époque de construction et date de vente comparables.",
                                S['small'])]

        # Renovation scenario
        if after:
            sim = v['sim']
            lines = [d for d in sim['detailed_costs'] if d['id'] != 'parking']
            extras = [d for d in sim['detailed_costs'] if d['id'] == 'parking']
            fig = display_figures(sim, lines, extras)
            work_rows = [kv(text(d['name']), eur_range(d['cost_low'], d['cost_high'])) for d in lines]
            work_rows += [kv(text(d['name']), eur_r(d['cost'], 10)) for d in extras]
            work_rows += [
                kv('<b>Coût des travaux</b>', f"<b>{eur_span(fig['cost_low'], fig['cost_high'])}</b>"),
                kv('Aides estimées', f"<font color='#3E8E63'>−{NBSP}{eur_span(fig['aids_low'], fig['aids_high'])}</font>"),
                kv('<b>Reste à charge</b>', f"<b>{eur_span(fig['rest_low'], fig['rest_high'])}</b>"),
            ]
            story += [CondPageBreak(7 * cm), Spacer(1, 18), next_section('Le scénario de rénovation'), Spacer(1, 8),
                      Paragraph(f"Travaux permettant de passer de la classe {v['current_label']} à la classe {v['target_label']}"
                                f" ({num(sim['initial_cep'])} → {num(sim['new_cep'])}{NBSP}kWh/m²/an).", S['muted']), Spacer(1, 6),
                      rows_table(work_rows, [CONTENT_W * 0.6, CONTENT_W * 0.4]), Spacer(1, 3),
                      Paragraph(f"Aides : {text(sim['aid_rules'])}, catégorie de revenus « {text(sim['income_profile'])} ». "
                                "Coûts : prix moyens de marché ; seuls des devis fixent le prix réel.", S['small'])]

        # Method and signature
        contact = ' · '.join(x for x in [text(agency.get('agent_name') or ''), text(agency.get('phone') or ''), text(agency.get('email') or '')] if x)
        story += [CondPageBreak(5 * cm), Spacer(1, 18), next_section('Méthode et réserves'), Spacer(1, 8), *bullet_list([
            f"Valeur estimée à partir des ventes réelles publiées (DVF), d'un seul logement du même type{similar}, au plus près du bien"
            + (", prix ramenés au dernier trimestre connu." if adjusted else "."),
            "Correction selon la classe DPE du bien, à partir des écarts de prix mesurés entre classes sur les ventes rapprochées de leur DPE. "
            "Après travaux, 70 % de l'écart entre la classe actuelle et la classe visée sont retenus : le reste tient à l'état général des "
            "logements vendus, que les travaux énergétiques seuls n'apportent pas. Le gain retenu ne dépasse jamais deux fois le coût des travaux.",
            "Fourchette : entre le premier et le troisième quart des prix au m² des ventes comparables.",
            "Cet avis de valeur ne constitue pas une expertise immobilière. Il ne tient compte que des éléments indiqués et de l'ajustement du conseiller ;"
            " l'état réel, les prestations et la situation précise du bien peuvent modifier sa valeur.",
        ], 'muted'), Spacer(1, 14),
            boxed([Paragraph(f"<b>{text(agency.get('agency_name') or '')}</b>", S['body'])] + ([Paragraph(contact, S['muted'])] if contact else []),
                  rule=BRASS_LIGHT, padding=10)]

        brand = agency.get('agency_name') or 'SPREA'
        doc.build(story, onFirstPage=_paper, onLaterPages=_paper,
                  canvasmaker=lambda *a, **k: NumberedCanvas(*a, address=address['full'], brand=brand, subtitle='Avis de valeur', **k))
        return buffer.getvalue()


    # --- Dossier d'investissement (Pro, agency branding) ---

    def generate_investment(self, d: Dict[str, Any]) -> bytes:
        buffer = BytesIO()
        agency = d.get('agency') or {}
        address = d['address']
        v, sim, market, thesis = d['valuation'], d['sim'], d['market'], d['thesis']
        brand = agency.get('agency_name') or 'SPREA'
        # Same figures, told to whoever reads them: the investor client of the
        # agency, the buyer of a dwelling under mandate, or its owner
        audience = d.get('audience') or 'investisseur'
        title = INVESTMENT_TITLES[audience]
        investor = audience == 'investisseur'
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                                topMargin=HEADER_H + 1.0 * cm, bottomMargin=2.3 * cm,
                                title=f"{title} – {address['full']}", author=brand)
        kicker = f"{title} · {text(d['profile_name'])}" if investor else title
        story: List[Any] = [Paragraph(kicker, style('kicker', fontSize=9, textColor=BRASS)),
                            Paragraph(text(address['street']), S['address'])]
        if address['locality']:
            story.append(Paragraph(text(address['locality']), style('loc', fontName='Serif', fontSize=13, leading=17, textColor=MUTED)))
        facts = ' · '.join(x for x in [
            text(d['kind'] or 'Logement'), f"{d['surface']:g}".replace('.', ',') + f"{NBSP}m²", text(d.get('period') or ''),
            f"DPE {text(d['label'])} du {text(date.fromisoformat(d['dpe_date']).strftime('%d/%m/%Y'))}" if d.get('dpe_date') else f"DPE {text(d['label'])}",
            f"n° {text(d['number'])}",
        ] if x)
        story += [Spacer(1, 4), Paragraph(facts, S['meta'])]
        if d.get('client_name'):
            story.append(Paragraph(f"Établi pour {text(d['client_name'])}", S['meta']))
        story.append(Spacer(1, 14))

        # Synthesis
        margin = d['margin']
        good = margin > 0
        # "Marge" speaks to a dealer; a buyer or an owner reads a potential gain
        gain_label = ('Marge brute' if good else 'Bilan') if investor else ('Plus-value potentielle' if good else 'Écart valeur / coût')
        price_label = ("Prix d'acquisition" + (' demandé' if d.get('price_is_asked') else ' estimé')) if audience != 'proprietaire' \
            else ('Prix de vente envisagé' if d.get('price_is_asked') else 'Valeur estimée aujourd\'hui')
        color = '#3E8E63' if good else '#C4553A'
        small = style('ks', fontSize=7.5, leading=10, textColor=MUTED)
        w = (CONTENT_W - 24) / 4
        cells = [
            [*kpi_cell(price_label, f"{eur(d['price'])}"),
             Paragraph(f"classe {text(d['label'])}, {eur(round(d['price'] / d['surface']))}/m²", small)],
            [*kpi_cell('Budget total', f"{eur(d['total'])}"),
             Paragraph("achat, notaire et travaux" + (", aides déduites" if d['aids'] else ""), small)],
            [*kpi_cell(f"Valeur après travaux (classe {text(d['new_label'])})", f"{eur(d['resale'])}"),
             Paragraph(f"entre {eur(d['resale_low'])} et {eur(d['resale_high'])}" if d['resale_low'] != d['resale_high'] else '', small)],
            [*kpi_cell(gain_label, f"<font color='{color}'>{'+' if good else '−'}{NBSP}{eur(abs(margin))}</font>", big=True),
             Paragraph((f"{str(d['margin_pct']).replace('.', ',').replace('-', '−')}{NBSP}% du budget" if d.get('margin_pct') is not None else '')
                       + ", avant frais financiers et impôts", small)],
        ]
        kpis = Table([cells], colWidths=[w] * 4)
        kpis.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8),
                                  ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                                  ('BACKGROUND', (3, 0), (3, 0), TINT), ('LINEAFTER', (0, 0), (-2, 0), 0.5, LINE)]))
        secondary = [kv('Programme', f"{text(d['label'])} → <b>{text(d['new_label'])}</b> : " + text(', '.join(n[:1].lower() + n[1:] for n in d['works_names'])))]
        if d.get('rent_month'):
            secondary.append(kv('Loyer de marché estimé', f"{eur(d['rent_month'])} / mois · rendement brut "
                                f"<b>{str(d['gross_yield']).replace('.', ',')}{NBSP}%</b>"))
        secondary += [kv('Location aujourd\'hui', text(d['rental_now'])), kv('Location après travaux', text(d['rental_after']))]
        story += [KeepTogether([Paragraph('Synthèse', S['h2']), Spacer(1, 8),
                                boxed([kpis, Spacer(1, 8), rows_table(secondary, [CONTENT_W * 0.35 - 24, CONTENT_W * 0.65])])])]

        n = 0

        def next_section(title: str) -> Table:
            nonlocal n
            n += 1
            return section(n, title)

        # Thesis
        source_note = ("Note rédigée avec l'aide d'une intelligence artificielle (Claude, Anthropic) à partir des seuls chiffres de ce dossier, "
                       "à relire avec votre conseiller." if thesis.get('source') == 'claude'
                       else "Note établie automatiquement à partir des chiffres de ce dossier.")
        headings = THESIS_HEADINGS[audience]
        story += [CondPageBreak(8 * cm), Spacer(1, 18), next_section(headings['these']), Spacer(1, 4),
                  Paragraph(source_note, S['muted']), Spacer(1, 6),
                  boxed([Paragraph(text(thesis['these']), S['narrative'])], rule=BRASS_LIGHT, padding=10), Spacer(1, 8),
                  Paragraph('Points forts', S['narrative_h']), Spacer(1, 2), *bullet_list(thesis['points_forts']), Spacer(1, 6),
                  Paragraph(headings['risques'], S['narrative_h']), Spacer(1, 2), *bullet_list(thesis['risques']),
                  Spacer(1, 6), Paragraph(headings['strategie'], S['narrative_h']), Spacer(1, 2), Paragraph(text(thesis['strategie']), S['narrative']),
                  Spacer(1, 6), Paragraph(headings['arguments'], S['narrative_h']), Spacer(1, 2),
                  Paragraph(text(thesis.get('arguments') or thesis.get('negociation') or ''), S['narrative'])]

        # Financial plan
        rows = [kv("Prix d'acquisition" + (" (demandé)" if d.get('price_is_asked') else " (estimé)"), eur(d['price'])),
                kv(f"Frais de notaire (environ {round(d['notary_rate'] * 100)}{NBSP}%)", eur(d['notary'])),
                kv('Travaux TTC', eur(d['works']) + f" <font size='7.5' color='#8A93A3'>({eur(d['works_low'])} à {eur(d['works_high'])})</font>")]
        if d['aids']:
            rows.append(kv('Aides estimées', f"<font color='#3E8E63'>−{NBSP}{eur(d['aids'])}</font>"))
        rows += [kv('<b>Budget total</b>', f"<b>{eur(d['total'])}</b>"),
                 kv('Valeur estimée après travaux', eur(d['resale'])),
                 kv(f'<b>{gain_label}</b>', f"<font color='{color}'><b>{'+' if good else '−'}{NBSP}{eur(abs(margin))}</b></font>")]
        notes = []
        if d['profile'] == 'marchand':
            notes.append("Marchand de biens : frais de notaire réduits sous engagement de revendre dans les cinq ans ; une société n'a pas accès "
                         "à MaPrimeRénov', aucune aide n'est comptée. TVA sur marge, impôt sur les sociétés et frais de revente non déduits.")
        else:
            notes.append(("Investisseur bailleur : " if investor else "Acquéreur particulier : ")
                         + "aides de l'Anah et primes CEE comptées selon le barème en vigueur, catégorie de revenus "
                         "par défaut, à confirmer par France Rénov'. Fiscalité des loyers non comprise.")
        notes.append("Frais financiers (prêt, intérêts intercalaires), taxe foncière et charges non compris.")
        plan_intro = {"acheteur": "Ce que coûte le projet complet, achat et travaux, et ce que vaudra le bien une fois rénové.",
                      "proprietaire": "Le calcul que fera un acquéreur : achat, frais, travaux et aides, face à la valeur du bien une fois rénové."}
        story += [CondPageBreak(7 * cm), Spacer(1, 18), next_section('Le plan financier'), Spacer(1, 6)]
        if audience in plan_intro:
            story += [Paragraph(plan_intro[audience], S['muted']), Spacer(1, 6)]
        story += [rows_table(rows, [CONTENT_W * 0.6, CONTENT_W * 0.4], bold_last=True), Spacer(1, 4)] + \
                 [Paragraph(text(x), S['small']) for x in notes]

        # Rental scenario
        if d.get('rent_month'):
            story += [CondPageBreak(5 * cm), Spacer(1, 18), next_section('Le scénario locatif'), Spacer(1, 8), rows_table([
                kv('Loyer de marché (charges comprises)', f"{eur(d['rent_month'])} / mois"),
                kv('Fourchette de la commune', f"{eur(d['rent_month_low'])} à {eur(d['rent_month_high'])} / mois"),
                kv('Loyer au m²', f"{str(d['rent_m2']).replace('.', ',')}{NBSP}€/m²"
                   + (f" <font size='7.5' color='#8A93A3'>(commune : {str(d['rent_m2_commune']).replace('.', ',')}{NBSP}€/m²)</font>"
                      if d.get('rent_m2_commune') and d['rent_m2_commune'] != d['rent_m2'] else '')),
                kv('<b>Rendement brut sur le budget total</b>', f"<b>{str(d['gross_yield']).replace('.', ',')}{NBSP}%</b>"),
                kv('Location aujourd\'hui', text(d['rental_now'])),
                kv('Location après travaux', text(d['rental_after'])),
            ], [CONTENT_W * 0.6, CONTENT_W * 0.4]), Spacer(1, 3), Paragraph(
                "Loyer d'annonce prédit pour la commune (« Carte des loyers », ANIL et ministère du Logement), charges comprises, "
                "ramené à la surface du logement : un grand logement se loue moins cher au m², un petit plus cher. "
                "Dans les communes en zone tendue, l'encadrement ou le plafonnement des loyers peut s'appliquer.", S['small'])]

        # Works programme
        works = [[head('Travaux'), head('Fourchette TTC', 2)]]
        for c in sim['detailed_costs']:
            works.append([Paragraph(text(c['name']), S['body']), Paragraph(eur_range(c['cost_low'], c['cost_high']), S['right'])])
        works.append([Paragraph('<b>Total</b>', S['body']), Paragraph(f"<b>{eur_range(sim['cost_low'], sim['cost_high'])}</b>", S['right'])])
        story += [CondPageBreak(6 * cm), Spacer(1, 18), next_section('Le programme de travaux'), Spacer(1, 8),
                  Paragraph(f"Programme simulé à partir du DPE pour passer de la classe {text(d['label'])} à la classe {text(d['new_label'])} "
                            f"({num(sim['initial_cep'])} → {num(sim['new_cep'])}{NBSP}kWh/m²/an). Durée indicative : {days(sim.get('duration_days'))}.",
                            S['muted']), Spacer(1, 6),
                  grid(works, [CONTENT_W * 0.7, CONTENT_W * 0.3], bold_last=True), Spacer(1, 3),
                  Paragraph("Prix moyens du marché, TVA à 5,5 % : seuls des devis d'artisans RGE fixent le prix réel.", S['small'])]

        # Market and DPE effect
        rows = [kv('Prix médian au m² des ventes comparables', f"<b>{eur(market['price_per_m2'])}</b>"),
                kv('Moitié des ventes entre', f"{eur(market['q25'])} et {eur(market['q75'])} /m²"),
                kv('Ventes retenues', f"{num(market['sales'])} ventes {text(market['scope'])} ({text(market['period'])})"),
                kv(f"Prix au m² en classe {text(d['label'])}", eur(v['price_m2_now']))]
        story += [CondPageBreak(6 * cm), Spacer(1, 18), next_section('Le marché local'), Spacer(1, 8),
                  rows_table(rows, [CONTENT_W * 0.55, CONTENT_W * 0.45]), Spacer(1, 3),
                  Paragraph(f"Source : {text(market['source'])} (données DVF, DGFiP).", S['small'])]
        if market.get('comparables'):
            # What a buyer contests first is the value after works: the sales it rests on
            story += [Spacer(1, 10), Paragraph('Ventes comparables les plus proches', S['h3']), Spacer(1, 4),
                      comparables_table(market, market.get('adjusted', 'actualisées' in (market.get('source') or '')))]
        if v.get('class_premium'):
            prem = v['class_premium']
            cls_rows = [[head('Classe DPE'), *[head(c, 1) for c in LABELS]],
                        [Paragraph("Écart de prix vs D", S['body']),
                         *[Paragraph(("<b>" if c in (d['label'], d['new_label']) else '') + f"{prem[c]:+.0f}{NBSP}%".replace('+0', '0')
                                     + ("</b>" if c in (d['label'], d['new_label']) else ''), style(f'ip{c}', alignment=1)) for c in LABELS]]]
            story += [Spacer(1, 10), grid(cls_rows, [CONTENT_W * 0.30] + [CONTENT_W * 0.10] * 7), Spacer(1, 3),
                      Paragraph(f"Écarts de prix entre classes mesurés sur {num(v.get('class_sample') or 0)} ventes rapprochées de leur DPE. "
                                "Après travaux, 70 % de l'écart entre la classe actuelle et la classe visée sont retenus, dans la limite de "
                                "deux fois le coût des travaux.", S['small'])]

        # Method
        contact = ' · '.join(x for x in [text(agency.get('agent_name') or ''), text(agency.get('phone') or ''), text(agency.get('email') or '')] if x)
        story += [CondPageBreak(5 * cm), Spacer(1, 18), next_section('Méthode et réserves'), Spacer(1, 8), *bullet_list([
            "Valeur actuelle : prix au m² des ventes comparables (DVF), corrigé de l'écart de prix mesuré pour la classe DPE du bien.",
            "Valeur après travaux : même méthode à la classe atteinte, en ne retenant que 70 % de l'écart entre classes, et un gain "
            "qui ne dépasse jamais deux fois le coût des travaux : au-delà, l'écart de prix tient à l'état général du bien.",
            "Travaux et aides : moteur de simulation SPREA à partir du DPE publié par l'ADEME ; barème des aides en vigueur.",
            "Ce dossier est une estimation indicative : il ne constitue ni une expertise immobilière, ni un audit énergétique, ni un conseil en "
            "investissement. Visite, diagnostics, devis et étude de financement restent indispensables avant toute offre.",
        ], 'muted')]
        if agency.get('agency_name'):
            story += [Spacer(1, 14), boxed([Paragraph(f"<b>{text(agency['agency_name'])}</b>", S['body'])] + ([Paragraph(contact, S['muted'])] if contact else []),
                                           rule=BRASS_LIGHT, padding=10)]

        doc.build(story, onFirstPage=_paper, onLaterPages=_paper,
                  canvasmaker=lambda *a, **k: NumberedCanvas(*a, address=address['full'], brand=brand, subtitle=title, notice=INVESTMENT_NOTICE, **k))
        return buffer.getvalue()

pdf_service = PDFReportGenerator()
