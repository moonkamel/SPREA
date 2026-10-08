"""PDF report, in the site's visual identity (navy, brass, Source Serif + Inter).

The page body stays light (ivory) so the report prints well; the navy header
band and brass accents carry the brand.
"""
import os
import re
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


def format_narrative(raw: str) -> List[Paragraph]:
    """Turns the AI text (light markdown) into safe paragraphs; short standalone
    lines (titles, possibly in bold or after #) become headings."""
    out: List[Paragraph] = []
    current: List[str] = []

    def flush():
        if current:
            para = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', ' '.join(current)).replace('*', '')
            out.append(Paragraph(para, S['narrative']))
            current.clear()

    for line in escape(raw.strip()).splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        content = re.sub(r'^(#+|[-•])\s*', '', stripped).strip()
        plain = content.replace('*', '').strip()
        if (stripped.startswith('#') or re.fullmatch(r'\*\*.+\*\*:?', content)) or (len(plain) < 60 and not plain.endswith(('.', '!', '?', ':')) and not current):
            flush()
            out.append(Paragraph(plain.rstrip(':'), S['narrative_h']))
        else:
            current.append(content)
    flush()
    return out


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


# --- Report ---

NEXT_STEPS = [
    ("Faites-vous accompagner", "Contactez gratuitement un conseiller France Rénov' (france-renov.gouv.fr ou 0 808 800 700). Pour une rénovation d'ampleur, un Accompagnateur Rénov' est obligatoire."),
    ("Demandez des devis", "Sollicitez au moins deux artisans certifiés RGE pour chaque type de travaux : la certification conditionne les aides."),
    ("Réservez les primes CEE", "Acceptez l'offre de prime d'un fournisseur d'énergie avant de signer les devis."),
    ("Déposez MaPrimeRénov'", "Sur maprimerenov.gouv.fr, avant le début des travaux."),
    ("Financez le reste à charge", "Demandez un éco-prêt à taux zéro à une banque partenaire, avec vos devis."),
]


class PDFReportGenerator:
    def generate(self, data: Dict[str, Any]) -> bytes:
        buffer = BytesIO()
        address = str(data.get('address') or 'Adresse du bien')
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=HEADER_H + 1.0 * cm, bottomMargin=2.0 * cm,
            title=f"Rapport SPREA – {address}", author='SPREA',
        )
        story: List[Any] = []
        is_investor = data.get('user_profile') == 'investisseur'

        # Title
        meta = ' · '.join(x for x in [
            text(data.get('building_type', '')).capitalize(),
            f"{data['surface']:g}".replace('.', ',') + f"{NBSP}m²" if data.get('surface') else '',
            text(data.get('construction_period') if data.get('construction_period') not in (None, 'N/A') else data.get('year') if data.get('year') not in (None, 'N/A') else ''),
        ] if x)
        dpe_ref = ' · '.join(x for x in [
            f"DPE du {text(data['dpe_date'])}" if data.get('dpe_date') else 'DPE',
            f"n° {text(data['ademe_dpe_number'])}" if data.get('ademe_dpe_number') not in (None, 'N/A') else '',
        ] if x)
        story += [
            Paragraph(text(address), S['address']),
            Spacer(1, 4),
            Paragraph(meta, S['meta']),
            Paragraph(dpe_ref, style('ref', fontSize=8, textColor=FAINT)),
            Spacer(1, 16),
        ]

        # Summary
        gain = data.get('gain_classes') or 0
        labels = Table([[
            dpe_badge(data.get('current_label')),
            Paragraph('→', style('arrow', fontSize=18, alignment=1, textColor=FAINT, leading=20)),
            dpe_badge(data.get('new_label')),
            [Paragraph(f"<b>{'+' + str(gain) + ' classe' + ('s' if gain > 1 else '') if gain else 'Pas de changement de classe'}</b>", S['body']),
             Paragraph(f"{num(data.get('initial_cep'))} → {num(data.get('new_cep'))}{NBSP}kWh/m²/an", S['muted'])],
        ]], colWidths=[1.6 * cm, 1.0 * cm, 1.6 * cm, CONTENT_W - 4.2 * cm - 24])
        labels.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))

        aids = (data.get('subsidies') or 0) + (data.get('cee_est') or 0)
        roi = data.get('roi_years')
        kpi_w = (CONTENT_W - 24) / 4
        kpis = Table([
            [kpi_cell('Coût des travaux', eur(data.get('total_cost'))),
             kpi_cell('Aides estimées', f"<font color='#3E8E63'>−{NBSP}{eur(aids)}</font>"),
             kpi_cell('Reste à charge', eur(data.get('rest_to_pay')), big=True),
             kpi_cell('Économies d\'énergie', f"<font color='#3E8E63'>{eur(data.get('annual_savings'))}</font><font size='9' color='#5B6577'> / an</font>")],
        ], colWidths=[kpi_w] * 4)
        kpis.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (2, 0), (2, 0), TINT),
            ('LINEAFTER', (0, 0), (1, 0), 0.5, LINE),
        ]))

        if roi is None:
            roi_text = '–'
        elif roi < 1:
            roi_text = "moins d'un an"
        else:
            roi_text = f"{roi}{NBSP}ans"
        if data.get('ban_date'):
            climate = (f"<font color='#C4553A'>Location interdite dès {text(data['new_ban_year'])}</font>"
                       if data.get('new_ban_year') else "<font color='#3E8E63'>Logement de nouveau louable</font>")
        else:
            climate = 'Aucune interdiction prévue'
        secondary = rows_table([
            kv('Retour sur investissement', roi_text),
            kv('Valeur verte du bien', f"+{NBSP}{eur(data.get('latent_gain'))}" if data.get('latent_gain') else '–'),
            kv('Loi Climat après travaux', climate),
        ], [CONTENT_W * 0.55 - 24, CONTENT_W * 0.45])

        story.append(KeepTogether([
            Paragraph('Synthèse', S['h2']),
            Spacer(1, 8),
            boxed([labels, Spacer(1, 12), kpis, Spacer(1, 8), secondary]),
        ]))

        # AI analysis
        if data.get('ai_narrative'):
            story += [
                Spacer(1, 18),
                Paragraph("L'analyse de votre projet", S['h2']),
                Spacer(1, 8),
                boxed(format_narrative(data['ai_narrative']), rule=BRASS_LIGHT),
            ]

        # 1. Today
        today_rows = [
            kv('Étiquette énergie recalculée', f"<b>{text(data.get('current_label'))}</b>"),
            kv('Consommation', f"{num(data.get('initial_cep'))}{NBSP}kWh/m²/an"),
            kv('Émissions de CO₂', f"{num(data.get('ges_value'))}{NBSP}kg/m²/an"),
        ]
        if data.get('heating_energy'):
            today_rows.append(kv('Énergie de chauffage', text(data['heating_energy']).capitalize()))
        today_rows.append(kv("Facture d'énergie estimée", f"{eur(data.get('annual_bill_before'))} / an"))
        today = [section(1, "Le logement aujourd'hui"), Spacer(1, 8), rows_table(today_rows, [CONTENT_W * 0.6, CONTENT_W * 0.4])]
        if data.get('ban_date'):
            today += [Spacer(1, 8), boxed([Paragraph(
                f"<b>Loi Climat et Résilience :</b> les logements classés {text(data.get('current_label'))} ne peuvent plus être proposés "
                f"à la location à partir du {text(data['ban_date'])}.", S['body'])], background=colors.HexColor('#FBEDE8'), rule=CORAL, padding=9)]
        story += [CondPageBreak(7 * cm), Spacer(1, 18), KeepTogether(today)]

        # 2. Works
        works_rows = []
        for item in data.get('detailed_costs') or []:
            name = text(item.get('name', 'Travaux'))
            if item.get('suggested'):
                name += " <font size='7.5' color='#A8853F'>RECOMMANDÉ</font>"
            works_rows.append(kv(name, eur(item.get('cost'))))
        works_rows.append(kv('<b>Total des travaux TTC</b>', f"<b>{eur(data.get('total_cost'))}</b>"))
        works = [section(2, 'Les travaux retenus'), Spacer(1, 8),
                 rows_table(works_rows, [CONTENT_W * 0.7, CONTENT_W * 0.3], bold_last=True)]
        notes = []
        if data.get('duration_days'):
            notes.append(f"Durée indicative du chantier : {text(data['duration_days'])} jours ouvrés.")
        if data.get('has_iti'):
            notes.append("L'isolation des murs par l'intérieur réduit la surface habitable d'environ 1,5 %.")
        if notes:
            works += [Spacer(1, 6), Paragraph(' '.join(notes), S['muted'])]
        story += [CondPageBreak(6 * cm), Spacer(1, 18), KeepTogether(works)]

        if data.get('thresholds'):
            story += [Spacer(1, 14), KeepTogether([
                Paragraph('Effet sur l\'étiquette énergie', S['h3']), Spacer(1, 6),
                *dpe_scale(data['thresholds'], data.get('current_label'), data.get('new_label')),
                Spacer(1, 6),
                Paragraph(f"Facture d'énergie estimée : {eur(data.get('annual_bill_before'))} → "
                          f"<font color='#3E8E63'><b>{eur(data.get('annual_bill_after'))}</b></font> par an.", S['body']),
            ])]

        # 3. Financing
        pathway = data.get('aid_pathway')
        mpr_label = "MaPrimeRénov' rénovation d'ampleur" if pathway == 'accompagne' else "MaPrimeRénov' par geste"
        fin_rows = [
            kv('Coût des travaux', eur(data.get('total_cost'))),
            kv(mpr_label, f"<font color='#3E8E63'>−{NBSP}{eur(data.get('subsidies'))}</font>"),
        ]
        if data.get('cee_est'):
            fin_rows.append(kv('Primes CEE (estimation)', f"<font color='#3E8E63'>−{NBSP}{eur(data.get('cee_est'))}</font>"))
        fin_rows += [
            kv('<b>Reste à charge</b>', f"<font color='#A8853F'><b>{eur(data.get('rest_to_pay'))}</b></font>"),
        ]
        financing = [section(3, 'Le plan de financement'), Spacer(1, 8),
                     rows_table(fin_rows, [CONTENT_W * 0.7, CONTENT_W * 0.3], bold_last=True)]
        extra = []
        if pathway == 'accompagne':
            extra.append("Les primes CEE ne se cumulent pas avec la rénovation d'ampleur : l'Anah les intègre déjà dans MaPrimeRénov'.")
        if data.get('eco_ptz_amount'):
            extra.append(f"Éco-prêt à taux zéro mobilisable : jusqu'à {eur(data['eco_ptz_amount'])}, sans intérêts.")
        if data.get('income_profile'):
            extra.append(f"Catégorie de revenus retenue : {text(data['income_profile'])}.")
        for note in data.get('aid_notes') or []:
            extra.append(text(note))
        if extra:
            financing += [Spacer(1, 6)] + [Paragraph(e, S['muted']) for e in extra]
        story += [CondPageBreak(6 * cm), Spacer(1, 18), KeepTogether(financing)]

        # 4. Investor
        step = 4
        if is_investor:
            inv_w = CONTENT_W / 4
            inv = Table([[
                kpi_cell('Rendement brut', f"{(data.get('yield_brut') or 0):.1f}".replace('.', ',') + f"{NBSP}%"),
                kpi_cell('Trésorerie mensuelle', eur(data.get('cashflow'))),
                kpi_cell("Économie d'impôt", eur(data.get('tax_benefit'))),
                kpi_cell('Coût net après impôt', eur(data.get('net_investor_cost'))),
            ]], colWidths=[inv_w] * 4)
            inv.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                     ('LINEAFTER', (0, 0), (2, 0), 0.5, LINE), ('LEFTPADDING', (1, 0), (-1, 0), 8)]))
            story += [CondPageBreak(5 * cm), Spacer(1, 18), KeepTogether([
                section(step, 'La rentabilité locative'), Spacer(1, 10), inv, Spacer(1, 8),
                Paragraph(f"Sur la base d'un prix d'achat de {eur(data.get('purchase_price'))} et d'un loyer de "
                          f"{eur(data.get('monthly_rent'))} par mois. Trésorerie : loyer moins la mensualité d'un prêt "
                          "finançant le reste à charge (7 ans, 4,5 %), hors charges et impôts.", S['muted']),
            ])]
            step += 1

        # Next steps
        steps = [section(step, 'Prochaines étapes'), Spacer(1, 8)]
        for i, (title, body) in enumerate(NEXT_STEPS, 1):
            row = Table([[Paragraph(str(i), style('ns', fontName='Serif-SemiBold', fontSize=12, textColor=BRASS)),
                          [Paragraph(f"<b>{title}</b>", S['body']), Paragraph(body, S['muted'])]]],
                        colWidths=[0.8 * cm, CONTENT_W - 0.8 * cm])
            row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                     ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
            steps.append(row)
        story += [CondPageBreak(7 * cm), Spacer(1, 18), KeepTogether(steps)]

        # Disclaimer
        story += [Spacer(1, 18), Paragraph(
            "Simulation indicative fondée sur les données publiques de l'ADEME et des coûts moyens de marché. "
            "Ce document ne constitue ni un DPE, ni un audit énergétique réglementaire, ni un devis. "
            "Les montants d'aides (barème MaPrimeRénov' 2025) doivent être confirmés par France Rénov' "
            "ou un Accompagnateur Rénov' avant tout engagement.", S['small'])]

        doc.build(story, onFirstPage=_paper, onLaterPages=_paper,
                  canvasmaker=lambda *a, **k: NumberedCanvas(*a, address=address, **k))
        return buffer.getvalue()


pdf_service = PDFReportGenerator()
