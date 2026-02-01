from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.units import cm
from io import BytesIO

class PremiumPDFReport(SimpleDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self.header_color = colors.HexColor('#0A192F')  # Obsidian Navy
        self.accent_color = colors.HexColor('#2ECC71')  # Electric Emerald
        self.alert_red = colors.HexColor('#E74C3C')
        self.text_muted = colors.HexColor('#7F8C8D')

    def draw_house_icon(self, x, y, size):
        self.canv.setStrokeColor(self.accent_color)
        self.canv.setLineWidth(2)
        p = self.canv.beginPath()
        # Modern House Outline
        p.moveTo(x, y + size * 0.4)
        p.lineTo(x + size / 2, y + size)
        p.lineTo(x + size, y + size * 0.4)
        p.moveTo(x + size * 0.2, y + size * 0.4)
        p.lineTo(x + size * 0.2, y)
        p.lineTo(x + size * 0.8, y)
        p.lineTo(x + size * 0.8, y + size * 0.4)
        # Arrow part
        p.moveTo(x + size * 0.5, y + size * 0.2)
        p.lineTo(x + size * 0.5, y + size * 0.6)
        p.lineTo(x + size * 0.4, y + size * 0.5)
        p.moveTo(x + size * 0.5, y + size * 0.6)
        p.lineTo(x + size * 0.6, y + size * 0.5)
        self.canv.drawPath(p, stroke=1, fill=0)

    def beforePage(self):
        self.canv.saveState()
        # Top Bar (Header Background)
        self.canv.setFillColor(self.header_color)
        self.canv.rect(0, A4[1]-2.8*cm, A4[0], 2.8*cm, fill=1, stroke=0)
        
        # Decorative emerald triangle accent
        self.canv.setFillColor(self.accent_color)
        p = self.canv.beginPath()
        p.moveTo(A4[0], A4[1])
        p.lineTo(A4[0], A4[1]-2.8*cm)
        p.lineTo(A4[0]-5*cm, A4[1])
        self.canv.drawPath(p, fill=1, stroke=0)

        # House Icon with Arrow
        self.draw_house_icon(A4[0]-1.8*cm, A4[1]-1.6*cm, 0.8*cm)
        
        # Logo Text in Header
        self.canv.setFillColor(colors.white)
        self.canv.setFont('Helvetica-Bold', 26)
        self.canv.drawString(1.5*cm, A4[1]-1.3*cm, "SPREA")
        self.canv.setFont('Helvetica-Bold', 9)
        self.canv.setFillColor(colors.HexColor('#7F8C8D'))
        self.canv.drawString(1.5*cm, A4[1]-1.8*cm, "INTELLIGENT PROPERTY REPORT")
        
        # Bottom branding
        self.canv.setFont('Helvetica-Bold', 7)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawString(1.5*cm, 0.8*cm, "S P R E A   |   A N A L Y S E   F I N T E C H")
        self.canv.drawRightString(A4[0]-1.5*cm, 0.8*cm, f"PAGE {self.canv.getPageNumber()}")
        
        self.canv.restoreState()

class PDFReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.colors = {
            'navy': colors.HexColor('#0A192F'),
            'emerald': colors.HexColor('#2ECC71'),
            'white': colors.white,
            'slate': colors.HexColor('#7F8C8D'),
            'red': colors.HexColor('#E74C3C'),
            'pale_red': colors.HexColor('#fee2e2'),
            'glass_bg': colors.HexColor('#f8fafc'),
            'blue_accent': colors.HexColor('#3B82F6')
        }
        self.section_header_style = ParagraphStyle(
            'SectionHeader',
            fontSize=16,
            textColor=self.colors['navy'],
            spaceBefore=20,
            spaceAfter=12,
            fontName='Helvetica-Bold',
            alignment=0,
            textTransform='uppercase',
            letterSpacing=1.5
        )
        self.body_style = ParagraphStyle(
            'BodyStyle',
            fontSize=10,
            textColor=self.colors['navy'],
            leading=14
        )
        self.card_label_style = ParagraphStyle(
            'CardLabel',
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=self.colors['slate'],
            textTransform='uppercase',
            alignment=0
        )
        self.card_value_style = ParagraphStyle(
            'CardValue',
            fontSize=18,
            fontName='Helvetica-Bold',
            textColor=self.colors['navy'],
            alignment=0
        )
        self.enormous_gain_style = ParagraphStyle(
            'EnormousGain',
            fontSize=34,
            fontName='Helvetica-Bold',
            textColor=self.colors['emerald'],
            alignment=0
        )
        self.hero_badge_style = ParagraphStyle(
            'HeroBadgeText',
            fontSize=42,
            textColor=colors.white,
            fontName='Helvetica-Bold',
            alignment=1
        )

    def get_dpe_color(self, label):
        colors_map = {
            'A': '#22c55e', 'B': '#84cc16', 'C': '#2ECC71', 'D': '#facc15', 
            'E': '#fb923c', 'F': '#f87171', 'G': '#dc2626',
        }
        return colors.HexColor(colors_map.get(str(label).upper(), '#cbd5e1'))

    def create_glass_card(self, label, value):
        data = [[Paragraph(label, self.card_label_style)], [Paragraph(value, self.card_value_style)]]
        t = Table(data, colWidths=[4.8*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), self.colors['glass_bg']),
            ('ROUNDEDCORNERS', [12, 12, 12, 12]),
            ('TOPPADDING', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('LEFTPADDING', (0,0), (-1,-1), 15),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ]))
        return t

    def create_energy_visualization(self, current_val, target_val, max_val=500):
        bar_width = 8*cm
        current_w = (min(current_val, max_val) / max_val) * bar_width
        target_w = (min(target_val, max_val) / max_val) * bar_width
        
        def bar(w, color):
            return Table([['']], colWidths=[w], rowHeights=[0.4*cm], style=[
                ('BACKGROUND', (0,0), (-1,-1), color),
                ('ROUNDEDCORNERS', [4, 4, 4, 4]),
            ])

        data = [
            [Paragraph("CONSOMMATION ACTUELLE", self.card_label_style), bar(current_w, self.colors['red']), Paragraph(f"<b>{current_val:.0f}</b>", self.body_style)],
            [Paragraph("APRÈS TRAVAUX", self.card_label_style), bar(target_w, self.colors['emerald']), Paragraph(f"<b>{target_val:.0f}</b>", self.body_style)]
        ]
        t = Table(data, colWidths=[4*cm, 8*cm, 1.5*cm])
        t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
        return t

    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = PremiumPDFReport(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=3.2*cm, bottomMargin=2*cm)
        elements = []

        # --- HERO ADDRESS ---
        elements.append(Spacer(1, -2.2*cm))
        elements.append(Paragraph(data.get('address', '').upper(), ParagraphStyle('Addr', fontSize=20, textColor=colors.white, fontName='Helvetica-Bold')))
        elements.append(Spacer(1, 1.8*cm))
        
        # Section 1: Property Snapshot
        cards = [[self.create_glass_card("Surface", f"{data.get('surface', 0)} m²"), 
                  self.create_glass_card("Type", data.get('building_type', 'Logement')), 
                  self.create_glass_card("Construction", data.get('construction_period') or 'N/A')]]
        elements.append(Table(cards, colWidths=[5.4*cm]*3))
        
        if data.get('ban_date'):
            elements.append(Spacer(1, 15))
            elements.append(Paragraph(
                f"<b>ALERTE LOCATION :</b> Interdit à la mise en location dès le <u>{data.get('ban_date')}</u>", 
                ParagraphStyle('AlertBanner', fontSize=11, textColor=colors.white, fontName='Helvetica-Bold', alignment=1, backColor=self.colors['red'], borderPadding=12, borderRadius=8)
            ))

        # Section 2: Energy Performance Target
        elements.append(Paragraph("Objectif Performance Énergétique", self.section_header_style))
        
        # Multi-stage SVG-like Badge
        label = data.get('new_label', 'G')
        color = self.get_dpe_color(label)
        dpe_badge = Table([[Paragraph(str(label), self.hero_badge_style)]], colWidths=[2.8*cm], rowHeights=[2.8*cm])
        dpe_badge.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), color), ('ROUNDEDCORNERS', [15, 15, 15, 15]), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        
        hero_data = [[dpe_badge, [
            Paragraph("VALEUR ESTIMÉE DU GAIN", self.card_label_style),
            Paragraph(f"+{data.get('latent_gain', 0):,.0f} €", self.enormous_gain_style),
            Paragraph(f"Économie : <b>{round(data.get('annual_savings', 0)):,.0f}€/an</b>", self.body_style),
            Spacer(1, 12),
            self.create_energy_visualization(data.get('initial_cep', 400), data.get('new_cep', 100))
        ]]]
        elements.append(Table(hero_data, colWidths=[4*cm, 13*cm], style=[('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (1,0), (1,0), 25)]))

        # Section 3: IA Analysis
        if data.get('ai_narrative') and "Erreur" not in data.get('ai_narrative'):
            elements.append(Paragraph("Analyse Stratégique SPREA", self.section_header_style))
            elements.append(Paragraph(data.get('ai_narrative'), ParagraphStyle('AI', leading=14, fontSize=10, backColor=colors.HexColor('#f0f9ff'), borderPadding=15, borderRadius=10)))

        # Section 4: Key Metrics
        elements.append(Spacer(1, 15))
        metrics = [[
            self.create_glass_card("Rentabilité Brut", f"{data.get('yield_brut', 0):.1f} %"),
            self.create_glass_card("Payback Travaux", f"{data.get('roi_years', 0)} ans"),
            self.create_glass_card("DPE ADEME", data.get('ademe_dpe_number', 'N/A')[:10])
        ]]
        elements.append(Table(metrics, colWidths=[5.4*cm]*3))

        # Section 5: Financial Breakdown
        elements.append(Paragraph("Plan de Financement Global", self.section_header_style))
        fin_rows = []
        if data.get('purchase_price', 0) > 0:
            fin_rows.append([Paragraph("<b>PRIX D'ACQUISITION DU BIEN</b>", self.body_style), Paragraph(f"<b>{data.get('purchase_price', 0):,.0f} €</b>", self.body_style)])
        
        for item in data.get('detailed_costs', []):
            fin_rows.append([Paragraph(item.get('name', 'Travaux'), self.body_style), Paragraph(f"{item.get('cost', 0):,.0f} €", self.body_style)])
        
        fin_rows.append([HRFlowable(width="100%", thickness=1, color=self.colors['navy']), HRFlowable(width="100%", thickness=1, color=self.colors['navy'])])
        fin_rows.append([Paragraph("<b>TOTAL TRAVAUX (BRUT)</b>", self.body_style), Paragraph(f"<b>{data.get('total_cost', 0):,.0f} €</b>", self.body_style)])
        
        fin_rows.append([Spacer(1, 5), Spacer(1, 5)])
        fin_rows.append([Paragraph("AIDES & DÉDUCTIONS ESTIMÉES", self.card_label_style), ""])
        fin_rows.append([Paragraph("MaPrimeRénov'", self.body_style), Paragraph(f"<font color='#2ECC71'>- {data.get('subsidies', 0):,.0f} €</font>", self.body_style)])
        if data.get('cee_est'):
            fin_rows.append([Paragraph("Primes CEE (à percevoir)", self.body_style), Paragraph(f"{data.get('cee_est', 0):,.0f} €", self.body_style)])
        
        t_fin = Table(fin_rows, colWidths=[12*cm, 5*cm])
        t_fin.setStyle(TableStyle([('ALIGN', (1,0), (1,-1), 'RIGHT'), ('BOTTOMPADDING', (0,0), (-1,-1), 6), ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#fcfcfc')])]))
        elements.append(t_fin)
        
        # Result Box
        elements.append(Spacer(1, 10))
        res_box = [[Paragraph("RESTE À CHARGE FINAL", ParagraphStyle('RL', fontSize=10, textColor=colors.white, fontName='Helvetica-Bold')), 
                    Paragraph(f"{data.get('rest_to_pay', 0):,.0f} €", ParagraphStyle('RV', fontSize=24, textColor=colors.white, fontName='Helvetica-Bold', alignment=2))]]
        t_res = Table(res_box, colWidths=[10*cm, 7*cm])
        t_res.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), self.colors['blue_accent']), ('ROUNDEDCORNERS', [10, 10, 10, 10]), ('TOPPADDING', (0,0), (-1,-1), 15), ('BOTTOMPADDING', (0,0), (-1,-1), 15), ('LEFTPADDING', (0,0), (-1,-1), 20), ('RIGHTPADDING', (0,0), (-1,-1), 20)]))
        elements.append(t_res)

        doc.build(elements)
        buffer.seek(0)
        return buffer.read()

pdf_service = PDFReportGenerator()
