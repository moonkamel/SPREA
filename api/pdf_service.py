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
        self.text_muted = colors.HexColor('#7F8C8D')
        self.property_address = ""

    def draw_house_icon(self, x, y, size):
        self.canv.setStrokeColor(self.accent_color)
        self.canv.setLineWidth(2)
        p = self.canv.beginPath()
        # Modern House Outline
        p.moveTo(x, y + size * 0.4)
        p.lineTo(x + size / 2, y + size)
        p.lineTo(x + size, y + size * 0.4)
        # Walls
        p.moveTo(x + size * 0.2, y + size * 0.4)
        p.lineTo(x + size * 0.2, y)
        p.lineTo(x + size * 0.8, y)
        p.lineTo(x + size * 0.8, y + size * 0.4)
        self.canv.drawPath(p, stroke=1, fill=0)

    def beforePage(self):
        self.canv.saveState()
        # Header Background
        self.canv.setFillColor(self.header_color)
        self.canv.rect(0, A4[1]-3.5*cm, A4[0], 3.5*cm, fill=1, stroke=0)
        
        # Emerald Accent
        self.canv.setFillColor(self.accent_color)
        p = self.canv.beginPath()
        p.moveTo(A4[0], A4[1])
        p.lineTo(A4[0], A4[1]-3.5*cm)
        p.lineTo(A4[0]-6*cm, A4[1])
        self.canv.drawPath(p, fill=1, stroke=0)

        # Centered Branding & Address
        self.canv.setFillColor(colors.white)
        self.canv.setFont('Helvetica-Bold', 28)
        self.canv.drawCentredString(A4[0]/2, A4[1]-1.2*cm, "SPREA")
        
        self.canv.setFont('Helvetica-Bold', 10)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawCentredString(A4[0]/2, A4[1]-1.7*cm, "INTELLIGENT PROPERTY REPORT")
        
        self.canv.setFillColor(colors.white)
        self.canv.setFont('Helvetica-Bold', 16)
        self.canv.drawCentredString(A4[0]/2, A4[1]-2.6*cm, str(self.property_address).upper())

        # House Icon (kept at top right for balance)
        self.draw_house_icon(A4[0]-1.8*cm, A4[1]-1.8*cm, 0.8*cm)
        
        # Footer
        self.canv.setFont('Helvetica-Bold', 7)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawCentredString(A4[0]/2, 0.8*cm, f"S P R E A   |   A N A L Y S E   F I N T E C H   |   PAGE {self.canv.getPageNumber()}")
        
        self.canv.restoreState()

class PDFReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.colors = {
            'navy': colors.HexColor('#0A192F'),
            'emerald': colors.HexColor('#2ECC71'),
            'blue_accent': colors.HexColor('#3B82F6'),
            'slate': colors.HexColor('#7F8C8D'),
            'light_gray': colors.HexColor('#F8FAFC'),
            'red': colors.HexColor('#E74C3C'),
            'pale_red': colors.HexColor('#fee2e2')
        }
        self.page_header_style = ParagraphStyle(
            'PageHeader',
            fontSize=18,
            textColor=self.colors['navy'],
            fontName='Helvetica-Bold',
            alignment=1,
            spaceAfter=20,
            textTransform='uppercase'
        )
        self.section_header_style = ParagraphStyle(
            'SectionHeader',
            fontSize=14,
            textColor=self.colors['navy'],
            fontName='Helvetica-Bold',
            alignment=1,
            spaceBefore=15,
            spaceAfter=15,
            textTransform='uppercase',
            letterSpacing=1.2
        )
        self.body_style = ParagraphStyle(
            'BodyStyle',
            fontSize=10,
            textColor=self.colors['navy'],
            leading=14,
            alignment=1
        )
        self.card_label_style = ParagraphStyle(
            'CardLabel',
            fontSize=7,
            fontName='Helvetica-Bold',
            textColor=self.colors['slate'],
            textTransform='uppercase',
            alignment=1
        )
        self.card_value_style = ParagraphStyle(
            'CardValue',
            fontSize=14,
            fontName='Helvetica-Bold',
            textColor=self.colors['navy'],
            alignment=1
        )
        self.gain_val_style = ParagraphStyle(
            'GainVal',
            fontSize=36,
            fontName='Helvetica-Bold',
            textColor=self.colors['emerald'],
            alignment=1
        )
        self.focus_title_style = ParagraphStyle(
            'FocusTitle',
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=self.colors['blue_accent'],
            alignment=1,
            spaceAfter=8
        )
        self.focus_body_style = ParagraphStyle(
            'FocusBody',
            fontSize=10,
            textColor=self.colors['navy'],
            leading=15,
            alignment=4, # Justified
            leftIndent=2*cm,
            rightIndent=2*cm
        )

    def get_dpe_color(self, label):
        colors_map = {
            'A': '#22c55e', 'B': '#84cc16', 'C': '#2ECC71', 'D': '#facc15', 
            'E': '#fb923c', 'F': '#f87171', 'G': '#dc2626',
        }
        return colors.HexColor(colors_map.get(str(label).upper(), '#cbd5e1'))

    def create_metric_card(self, label, value):
        data = [[Paragraph(label, self.card_label_style)], [Paragraph(value, self.card_value_style)]]
        t = Table(data, colWidths=[2.8*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), self.colors['light_gray']),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        return t

    def create_energy_visualization(self, current_val, target_val, max_val=500):
        bar_width = 7*cm
        current_w = (min(current_val, max_val) / max_val) * bar_width
        target_w = (min(target_val, max_val) / max_val) * bar_width
        
        def bar(w, color):
            return Table([['']], colWidths=[w], rowHeights=[0.4*cm], style=[
                ('BACKGROUND', (0,0), (-1,-1), color),
                ('ROUNDEDCORNERS', [4, 4, 4, 4]),
            ])

        data = [
            [Paragraph("ACTUEL", self.card_label_style), bar(current_w, self.colors['red']), Paragraph(f"<b>{current_val:.0f}</b>", self.body_style)],
            [Paragraph("APRÈS", self.card_label_style), bar(target_w, self.colors['emerald']), Paragraph(f"<b>{target_val:.0f}</b>", self.body_style)]
        ]
        t = Table(data, colWidths=[2.5*cm, 7*cm, 1.5*cm])
        t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER')]))
        return t

    def generate(self, data: dict) -> bytes:
        address_to_use = data.get('address', 'ADRESSE INCONNUE').upper()
        
        class FixedPremiumPDFReport(PremiumPDFReport):
            def __init__(self, *args, **kwargs):
                self.property_address = address_to_use
                super().__init__(*args, **kwargs)

        buffer = BytesIO()
        doc = FixedPremiumPDFReport(buffer, pagesize=A4, rightMargin=2.5*cm, leftMargin=2.5*cm, topMargin=4.5*cm, bottomMargin=2.5*cm)
        elements = []

        # --- PAGE 1: STRATEGIC DASHBOARD ---
        elements.append(Spacer(1, 0.5*cm))
        
        # Row of 6 cards
        row_cards = [[
            self.create_metric_card("Surface", f"{data.get('surface', 0)}m²"),
            self.create_metric_card("Type", data.get('building_type', 'N/A')),
            self.create_metric_card("Construction", (data.get('construction_period') or 'N/A')[:10]),
            self.create_metric_card("Rentabilité", f"{data.get('yield_brut', 0):.1f}%"),
            self.create_metric_card("Payback", f"{data.get('roi_years', 0)} ans"),
            self.create_metric_card("DPE ADEME", data.get('ademe_dpe_number', 'N/A')[-6:])
        ]]
        t_cards = Table(row_cards, colWidths=[2.8*cm]*6)
        t_cards.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
        elements.append(t_cards)

        # Rental Alert Banner
        if data.get('ban_date'):
            elements.append(Spacer(1, 20))
            elements.append(Paragraph(
                f"ALERTE LOCATION : Interdit à la mise en location dès le {data.get('ban_date')}", 
                ParagraphStyle('AlertBanner', fontSize=10, textColor=colors.white, fontName='Helvetica-Bold', alignment=1, backColor=self.colors['red'], borderPadding=12, borderRadius=10)
            ))

        # Energy Performance Section
        elements.append(Spacer(1, 30))
        elements.append(Paragraph("Objectif Performance Énergétique", self.section_header_style))
        
        # Large Badge
        label = data.get('new_label', 'G')
        color = self.get_dpe_color(label)
        dpe_badge = Table([[Paragraph(str(label), ParagraphStyle('Badge', fontSize=48, textColor=colors.white, fontName='Helvetica-Bold', alignment=1))]], colWidths=[3*cm], rowHeights=[3*cm])
        dpe_badge.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), color), ('ROUNDEDCORNERS', [15, 15, 15, 15]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        
        hero_table = [[
            dpe_badge,
            [
                Paragraph("VALEUR ESTIMÉE DU GAIN", self.card_label_style),
                Paragraph(f"+{data.get('latent_gain', 0):,.0f} €", self.gain_val_style),
                Paragraph(f"ÉCONOMIE ANNUELLE : <b>{round(data.get('annual_savings', 0)):,.0f} €</b>", self.body_style),
            ],
            self.create_energy_visualization(data.get('initial_cep', 400), data.get('new_cep', 100))
        ]]
        t_hero = Table(hero_table, colWidths=[4*cm, 6*cm, 6*cm])
        t_hero.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER')]))
        elements.append(t_hero)

        # --- PAGE 2: FINANCIAL PLAN ---
        elements.append(PageBreak())
        elements.append(Paragraph("Plan de Financement Global", self.page_header_style))
        
        fin_rows = []
        if data.get('purchase_price', 0) > 0:
            fin_rows.append([Paragraph("PRIX D'ACQUISITION DU BIEN", ParagraphStyle('L', fontSize=10, fontName='Helvetica-Bold')), Paragraph(f"{data.get('purchase_price', 0):,.0f} €", ParagraphStyle('R', fontSize=10, fontName='Helvetica-Bold', alignment=2))])
        
        for item in data.get('detailed_costs', []):
            fin_rows.append([Paragraph(item.get('name', 'Travaux'), self.body_style), Paragraph(f"{item.get('cost', 0):,.0f} €", ParagraphStyle('R', alignment=2))])
        
        fin_rows.append([HRFlowable(width="100%", thickness=1.5, color=self.colors['navy']), HRFlowable(width="100%", thickness=1.5, color=self.colors['navy'])])
        fin_rows.append([Paragraph("TOTAL TRAVAUX (BRUT)", ParagraphStyle('L', fontSize=11, fontName='Helvetica-Bold')), Paragraph(f"{data.get('total_cost', 0):,.0f} €", ParagraphStyle('R', fontSize=11, fontName='Helvetica-Bold', alignment=2))])
        
        fin_rows.append([Spacer(1, 15), Spacer(1, 15)])
        fin_rows.append([Paragraph("AIDES & DÉDUCTIONS ESTIMÉES", self.section_header_style), ""])
        fin_rows.append([Paragraph("MaPrimeRénov'", self.body_style), Paragraph(f"<font color='#2ECC71'>- {data.get('subsidies', 0):,.0f} €</font>", ParagraphStyle('R', alignment=2))])
        if data.get('cee_est'):
            fin_rows.append([Paragraph("Primes CEE (à percevoir)", self.body_style), Paragraph(f"- {data.get('cee_est', 0):,.0f} €", ParagraphStyle('R', alignment=2))])
        
        t_fin = Table(fin_rows, colWidths=[10*cm, 4*cm])
        t_fin.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,-1), 0.1, colors.HexColor('#E2E8F0')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')])
        ]))
        elements.append(t_fin)
        
        # Centered Huge Result Banner
        elements.append(Spacer(1, 30))
        res_table = [[Paragraph("RESTE À CHARGE FINAL", ParagraphStyle('RL', fontSize=12, textColor=colors.white, fontName='Helvetica-Bold', alignment=1)), 
                      Paragraph(f"{data.get('rest_to_pay', 0):,.1f} €", ParagraphStyle('RV', fontSize=32, textColor=colors.white, fontName='Helvetica-Bold', alignment=1))]]
        t_res = Table(res_table, colWidths=[14*cm])
        t_res.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), self.colors['blue_accent']),
            ('ROUNDEDCORNERS', [15, 15, 15, 15]),
            ('TOPPADDING', (0,0), (-1,-1), 25),
            ('BOTTOMPADDING', (0,0), (-1,-1), 25),
            ('ALIGN', (0,0), (-1,-1), 'CENTER')
        ]))
        elements.append(t_res)

        # --- PAGE 3: FOCUS SECTIONS ---
        if data.get('focus_mpr') or data.get('focus_cee') or data.get('focus_eco_ptz'):
            elements.append(PageBreak())
            elements.append(Paragraph("Détails des Aides Financières", self.page_header_style))
            elements.append(Spacer(1, 20))
            
            if data.get('focus_mpr'):
                elements.append(Paragraph("FOCUS MAPRIMERÉNOV'", self.focus_title_style))
                elements.append(Paragraph(data.get('focus_mpr'), self.focus_body_style))
                elements.append(Spacer(1, 40))
                
            if data.get('focus_cee'):
                elements.append(Paragraph("FOCUS PRIMES CEE", self.focus_title_style))
                elements.append(Paragraph(data.get('focus_cee'), self.focus_body_style))
                elements.append(Spacer(1, 40))
                
            if data.get('focus_eco_ptz'):
                elements.append(Paragraph("FOCUS ÉCO-PRÊT À TAUX ZÉRO", self.focus_title_style))
                elements.append(Paragraph(data.get('focus_eco_ptz'), self.focus_body_style))

        # Legal summary at absolute end
        elements.append(Spacer(1, 40))
        elements.append(Paragraph("Ce document est une simulation 3CL-2021. Il ne remplace pas un audit réglementaire.", 
                                  ParagraphStyle('L', fontSize=7, textColor=self.colors['slate'], alignment=1)))

        doc.build(elements)
        buffer.seek(0)
        return buffer.read()

pdf_service = PDFReportGenerator()
