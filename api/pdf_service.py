"""PDF report, in the site's visual identity (navy, brass, Source Serif + Inter).

The page body stays light (ivory) so the report prints well; the navy header
band and brass accents carry the brand.
"""
import os
from datetime import date
from io import BytesIO
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

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

    def __init__(self, *args, address: str = '', **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: List[dict] = []
        self.address = address

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
        self.drawString(MARGIN, PAGE_H - 1.18 * cm, 'SPREA')
        self.setFont('Inter', 8)
        self.setFillColor(BRASS_LIGHT)
        self.drawString(MARGIN + 1.9 * cm, PAGE_H - 1.15 * cm, 'Rapport de rénovation énergétique')
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




def eur_r(value: Optional[float], step: int = 100) -> str:
    """Estimates are shown rounded: 11 443 -> 11 400 €."""
    return eur(round((value or 0) / step) * step)


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

class PDFReportGenerator:
    def generate(self, report: Dict[str, Any], analysis: Dict[str, Any]) -> bytes:
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
        block: List[Any] = [next_section('Notre analyse'), Spacer(1, 8)]
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

        # 4. Financing
        story += [CondPageBreak(9 * cm), Spacer(1, 18), next_section('Le plan de financement'), Spacer(1, 8)]
        story += self._financing(report)

        # 5. Value
        story += [CondPageBreak(6 * cm), Spacer(1, 18),
                  next_section('Valeur et rentabilité locative' if report['is_investor'] else 'Valeur du bien'), Spacer(1, 8)]
        story += self._value(report)

        # 6. Steps
        steps: List[Any] = [next_section('Calendrier et prochaines étapes'), Spacer(1, 8)]
        for i, step in enumerate(report['steps'], 1):
            row = Table([[Paragraph(str(i), style('ns', fontName='Serif-SemiBold', fontSize=12, textColor=BRASS)),
                          [Paragraph(f"<b>{text(step['title'])}</b> <font color='#A8853F' size='8'>{text(step['when'])}</font>", S['body']),
                           Paragraph(text(step['text']), S['muted'])]]],
                        colWidths=[0.8 * cm, CONTENT_W - 0.8 * cm])
            row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                     ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
            steps.append(row)
        story += [CondPageBreak(8 * cm), Spacer(1, 18), *steps]

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
            f"étage {text(ident['floor'])}" if ident.get('floor') else '',
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

        aids = sim['subsidies'] + sim['cee_est']
        small = style('kpi_small', fontSize=7.5, leading=10, textColor=MUTED)
        kpi_w = (CONTENT_W - 24) / 4
        kpis = Table([[
            [*kpi_cell('Coût des travaux', f"≈{NBSP}{eur_r(sim['cost'])}"),
             Paragraph(f"entre {eur_r(sim['cost_low'])} et {eur_r(sim['cost_high'])}", small)],
            kpi_cell('Aides estimées', f"<font color='#3E8E63'>−{NBSP}{eur_r(aids)}</font>"),
            [*kpi_cell('Reste à charge', f"≈{NBSP}{eur_r(sim['rest_to_pay'])}", big=True),
             Paragraph(f"entre {eur_r(sim['rest_to_pay_low'])} et {eur_r(sim['rest_to_pay_high'])}", small)],
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

        roi = sim['roi_years']
        roi_text = '–' if roi is None else ("moins d'un an" if roi < 1 else f"environ {round(roi)}{NBSP}ans")
        green = f"+{NBSP}{eur_r(sim['latent_gain'], 500)}" if sim['latent_gain'] else '–'
        after_color = '#3E8E63' if sim['new_ban_date'] is None else '#C4553A'
        secondary = rows_table([
            kv('Retour sur investissement', roi_text),
            kv('Valeur verte du bien' + (" <font size='7.5' color='#8A93A3'>(indicative, voir section 5)</font>" if report['price_is_default'] else ''), green),
            kv('Location aujourd\'hui', text(sim['rental_status'])),
            kv('Location après travaux', f"<font color='{after_color}'>{text(sim['new_rental_status'])}</font>"),
        ], [CONTENT_W * 0.5 - 24, CONTENT_W * 0.5])

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
            kv('Étiquette DPE (énergie / climat)', f"<b>{text(sim['current_label'])}</b> "
                                                   f"<font color='#5B6577'>({text(sim['current_cep_label'])} / {text(sim['current_ges_label'])})</font>"),
            kv("Consommation d'énergie primaire", f"{num(sim['initial_cep'])}{NBSP}kWh/m²/an"),
            kv('Émissions de gaz à effet de serre', f"{num(sim['initial_ges'])}{NBSP}kg CO₂/m²/an"),
        ]
        for label, key in (('Chauffage', 'heating'), ('Eau chaude', 'hot_water'), ('Ventilation', 'ventilation')):
            if ident.get(key):
                rows.append(kv(label, text(ident[key])))
        rows.append(kv("Facture d'énergie estimée", f"{eur_r(sim['annual_bill_before'], 10)} / an"))
        if ident.get('dpe_annual_cost'):
            rows.append(kv('Coût annuel indiqué par le DPE', f"{eur(float(ident['dpe_annual_cost']))} / an"))
        out: List[Any] = [rows_table(rows, [CONTENT_W * 0.5, CONTENT_W * 0.5])]

        out += [Spacer(1, 14), KeepTogether([
            Paragraph('Où part la chaleur', S['h3']), Spacer(1, 2),
            Paragraph('Répartition des pertes de chaleur du logement, calculée à partir de son DPE.', S['muted']), Spacer(1, 6),
            share_bars(report['losses']),
        ])]

        usage_rows = [[head('Usage'), head("Aujourd'hui", 2), head('Après travaux', 2)]]
        for u in report['usages']:
            after = eur_r(u['eur_after'], 10)
            if u['energy_after'] != u['energy_before']:
                after += f" <font size='7.5' color='#8A93A3'>({text(u['energy_after'])})</font>"
            usage_rows.append([Paragraph(text(u['name']), S['body']), Paragraph(eur_r(u['eur_before'], 10), S['right']),
                               Paragraph(after, S['right'])])
        usage_rows.append([Paragraph('<b>Total par an</b>', S['body']),
                           Paragraph(f"<b>{eur_r(sum(u['eur_before'] for u in report['usages']), 10)}</b>", S['right']),
                           Paragraph(f"<font color='#3E8E63'><b>{eur_r(sum(u['eur_after'] for u in report['usages']), 10)}</b></font>", S['right'])])
        out += [Spacer(1, 14), KeepTogether([
            Paragraph('Votre facture par usage', S['h3']), Spacer(1, 6),
            grid(usage_rows, [CONTENT_W * 0.5, CONTENT_W * 0.25, CONTENT_W * 0.25], bold_last=True),
            Spacer(1, 3), Paragraph("Énergie facturée aux prix moyens actuels, hors abonnement.", S['small']),
        ])]

        reg = report['regulatory']
        calendar = ' · '.join(f"{label} : {d}" for label, d in reg['calendar'])
        out += [Spacer(1, 14), KeepTogether([
            Paragraph('Cadre réglementaire', S['h3']), Spacer(1, 6),
            rows_table([kv(text(i['label']), text(i['value'])) for i in reg['items']], [CONTENT_W * 0.32, CONTENT_W * 0.68]),
            Spacer(1, 3),
            Paragraph(f"Calendrier d'interdiction de louer (Loi Climat et Résilience), par classe : {text(calendar)}. "
                      "Il s'applique aux nouveaux baux et aux renouvellements.", S['small']),
        ])]
        return out

    def _works(self, report: Dict[str, Any]) -> List[Any]:
        sim = report['sim']
        works = report['works']
        if not works:
            return [Paragraph('Aucun travaux sélectionnés.', S['muted'])]
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
            if w['caution']:
                cell.append(Paragraph('À prévoir : ' + text(w['caution']), style('caut', fontSize=8.5, leading=12, textColor=CORAL)))
            rows.append([cell, Paragraph(eur_range(w['cost_low'], w['cost_high']), S['right'])])
        for extra in report['extra_costs']:
            rows.append([Paragraph(text(extra['name']), S['body']), Paragraph(eur_r(extra['cost'], 10), S['right'])])
        rows.append([Paragraph('<b>Total des travaux TTC</b>', S['body']),
                     Paragraph(f"<b>{eur_range(sim['cost_low'], sim['cost_high'])}</b>", S['right'])])
        table = grid(rows, [CONTENT_W * 0.7, CONTENT_W * 0.3], bold_last=True)
        table.setStyle(TableStyle([('VALIGN', (0, 1), (-1, -2), 'TOP')]))
        out.append(table)
        notes = []
        if sim.get('duration_days'):
            notes.append(f"Durée indicative du chantier : {text(sim['duration_days'])} jours ouvrés, hors délais d'approvisionnement.")
        notes.append("TVA à 5,5 % incluse. Fourchettes fondées sur les prix moyens du marché : seuls des devis fixent le prix réel.")
        out += [Spacer(1, 6), Paragraph(' '.join(notes), S['muted'])]

        if sim.get('thresholds'):
            out += [Spacer(1, 14), KeepTogether([
                Paragraph("Effet sur l'étiquette énergie", S['h3']), Spacer(1, 6),
                *dpe_scale(sim['thresholds'], sim['current_label'], sim['new_label']),
                Spacer(1, 6),
                Paragraph(f"Facture d'énergie estimée : {eur_r(sim['annual_bill_before'], 10)} → "
                          f"<font color='#3E8E63'><b>{eur_r(sim['annual_bill_after'], 10)}</b></font> par an.", S['body']),
            ])]
        return out

    def _financing(self, report: Dict[str, Any]) -> List[Any]:
        sim = report['sim']
        fin = report['financing']
        pathway = sim['aid_pathway']
        rows = [kv('Coût des travaux', eur_range(sim['cost_low'], sim['cost_high']))]
        if pathway == 'accompagne':
            rows.append(kv("MaPrimeRénov' rénovation d'ampleur", f"<font color='#3E8E63'>−{NBSP}{eur_r(sim['subsidies'])}</font>"))
        else:
            if sim['subsidies']:
                rows.append(kv("MaPrimeRénov' par geste", f"<font color='#3E8E63'>−{NBSP}{eur_r(sim['subsidies'])}</font>"))
            if sim['cee_est']:
                rows.append(kv('Primes CEE (estimation)', f"<font color='#3E8E63'>−{NBSP}{eur_r(sim['cee_est'])}</font>"))
            if not sim['subsidies'] and not sim['cee_est']:
                rows.append(kv('Aides', '–'))
        rows.append(kv('<b>Reste à charge</b>', f"<font color='#A8853F'><b>{eur_range(sim['rest_to_pay_low'], sim['rest_to_pay_high'])}</b></font>"))
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

        if sim['eco_ptz_amount']:
            loan = [
                kv('Éco-prêt à taux zéro', eur_r(sim['eco_ptz_amount'])),
                kv('Durée', f"{fin['eco_ptz_years']}{NBSP}ans"),
                kv('Mensualité', f"{eur(fin['eco_ptz_monthly'])} / mois"),
                kv('Économie sur la facture', f"<font color='#3E8E63'>−{NBSP}{eur(fin['monthly_saving'])} / mois</font>"),
            ]
            effort = fin['net_monthly_effort']
            loan.append(kv('<b>Effort mensuel net</b>', f"<b>{eur(effort)} / mois</b>" if effort > 0
                           else "<font color='#3E8E63'><b>Les économies couvrent la mensualité</b></font>"))
            out += [Spacer(1, 14), KeepTogether([
                Paragraph('Financer le reste à charge', S['h3']), Spacer(1, 6),
                rows_table(loan, [CONTENT_W * 0.6, CONTENT_W * 0.4], bold_last=True),
                Spacer(1, 3),
                Paragraph("Sans intérêts ni frais de dossier, sous conditions de la banque. Il se cumule avec MaPrimeRénov'.", S['small']),
            ])]
        return out

    def _value(self, report: Dict[str, Any]) -> List[Any]:
        sim = report['sim']
        roi = sim['roi_years']
        rows = [
            kv('Retour sur investissement', '–' if roi is None else f"environ {round(roi)}{NBSP}ans"),
            kv('Valeur verte estimée', f"+{NBSP}{eur_r(sim['latent_gain'], 500)}" if sim['latent_gain'] else '–'),
        ]
        out: List[Any] = [rows_table(rows, [CONTENT_W * 0.6, CONTENT_W * 0.4]), Spacer(1, 4),
                          Paragraph(f"Valeur verte : écart de prix constaté entre classes DPE, appliqué sur {eur(report['price_per_m2'])}/m²"
                                    + (" (prix par défaut : remplacez-le par le prix de votre secteur)." if report['price_is_default'] else "."),
                                    S['small'])]
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
                "mensualité d'un prêt finançant le reste à charge (7 ans, 4,5 %), hors charges et impôts. Économie d'impôt : "
                "déduction des travaux des revenus fonciers au taux marginal saisi.", S['muted'])]
        return out


pdf_service = PDFReportGenerator()
