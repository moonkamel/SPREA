from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.units import cm
from io import BytesIO

class PremiumPDFReport(SimpleDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self.header_color = colors.HexColor('#0f172a')  # Slate 900
        self.accent_color = colors.HexColor('#22c55e')  # Emerald 500
        self.text_muted = colors.HexColor('#64748b')

    def draw_house_icon(self, x, y, size):
        self.canv.setStrokeColor(colors.white)
        self.canv.setLineWidth(1.5)
        p = self.canv.beginPath()
        # Roof
        p.moveTo(x, y + size * 0.6)
        p.lineTo(x + size / 2, y + size)
        p.lineTo(x + size, y + size * 0.6)
        # Walls
        p.moveTo(x + size * 0.15, y + size * 0.6)
        p.lineTo(x + size * 0.15, y)
        p.lineTo(x + size * 0.85, y)
        p.lineTo(x + size * 0.85, y + size * 0.6)
        self.canv.drawPath(p, stroke=1, fill=0)

    def beforePage(self):
        self.canv.saveState()
        # Top Bar (Header Background)
        self.canv.setFillColor(self.header_color)
        self.canv.rect(0, A4[1]-2.5*cm, A4[0], 2.5*cm, fill=1, stroke=0)
        
        # Decorative dynamic shape (emerald triangle)
        self.canv.setFillColor(self.accent_color)
        p = self.canv.beginPath()
        p.moveTo(A4[0], A4[1])
        p.lineTo(A4[0], A4[1]-2.5*cm)
        p.lineTo(A4[0]-4*cm, A4[1])
        self.canv.drawPath(p, fill=1, stroke=0)

        # House Icon
        self.draw_house_icon(A4[0]-1.8*cm, A4[1]-1.5*cm, 0.8*cm)
        
        # Logo Text in Header
        self.canv.setFillColor(colors.white)
        self.canv.setFont('Helvetica-Bold', 22)
        self.canv.drawString(1.5*cm, A4[1]-1.4*cm, "SPREA")
        self.canv.setFont('Helvetica-Bold', 8)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawString(1.5*cm, A4[1]-1.85*cm, "INTELLIGENT PROPERTY REPORT")
        
        # Bottom branding
        self.canv.setFont('Helvetica-Bold', 7)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawString(1.5*cm, 0.8*cm, "S P R E A   |   A N A L Y S E   S T R A T É G I Q U E")
        self.canv.drawRightString(A4[0]-1.5*cm, 0.8*cm, f"PAGE {self.canv.getPageNumber()}")
        
        self.canv.restoreState()

class PDFReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'TitleStyle',
            parent=self.styles['Heading1'],
            fontSize=22,
            textColor=colors.white,
            spaceAfter=2,
            fontName='Helvetica-Bold',
            alignment=0,
            leading=26
        )
        self.section_header_style = ParagraphStyle(
            'SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#0f172a'), # Slate 900
            spaceBefore=14,
            spaceAfter=8,
            fontName='Helvetica-Bold',
            borderPadding=(0, 0, 4, 0),
            alignment=0,
            textTransform='uppercase'
        )
        self.body_style = ParagraphStyle(
            'BodyStyle',
            parent=self.styles['BodyText'],
            fontSize=9,
            textColor=colors.HexColor('#334155'), # Slate 700
            leading=12
        )
        self.card_label_style = ParagraphStyle(
            'CardLabel',
            fontSize=7,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#64748b'),
            textTransform='uppercase',
            alignment=0
        )
        self.card_value_style = ParagraphStyle(
            'CardValue',
            fontSize=16,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#0f172a'),
            alignment=0
        )
        self.metric_label_style = ParagraphStyle(
            'MetricLabel',
            parent=self.body_style,
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#94a3b8'),
            textTransform='uppercase',
            letterSpacing=0.5
        )
        self.badge_style = ParagraphStyle(
            'BadgeText',
            parent=self.body_style,
            fontSize=32,
            textColor=colors.white,
            fontName='Helvetica-Bold',
            alignment=1,
            leading=34
        )
        self.net_cost_style = ParagraphStyle(
            'NetCostStyle',
            parent=self.body_style,
            fontSize=22,
            textColor=colors.HexColor('#2563eb'),
            fontName='Helvetica-Bold',
            alignment=2
        )

    def get_dpe_color(self, label):
        colors_map = {
            'A': '#22c55e', 'B': '#84cc16', 'C': '#eab308', 'D': '#f59e0b', 
            'E': '#f97316', 'F': '#ef4444', 'G': '#b91c1c',
        }
        return colors.HexColor(colors_map.get(str(label).upper(), '#cbd5e1'))

    def create_metric_card(self, label, value, color_hex='#f8fafc'):
        """Creates a modern card widget for a single metric."""
        data = [[Paragraph(label, self.card_label_style)], [Paragraph(value, self.card_value_style)]]
        t = Table(data, colWidths=[4.2*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(color_hex)),
            ('ROUNDEDCORNERS', [8, 8, 8, 8]),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
        ]))
        return t

    def create_hero_dpe_badge(self, label):
        """Creates a large, prominent DPE badge."""
        color = self.get_dpe_color(label)
        data = [[Paragraph(str(label).upper(), self.badge_style)]]
        t = Table(data, colWidths=[2.2*cm], rowHeights=[2.2*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), color),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
        ]))
        return t

    def create_energy_bar(self, current_val, target_val, max_val=500):
        """Creates a visual bar chart comparison for energy consumption."""
        bar_width = 6*cm
        current_w = (min(current_val, max_val) / max_val) * bar_width
        target_w = (min(target_val, max_val) / max_val) * bar_width
        
        def bar(w, color):
            return Table([['']], colWidths=[w], rowHeights=[0.4*cm], style=[
                ('BACKGROUND', (0,0), (-1,-1), color),
                ('ROUNDEDCORNERS', [2, 2, 2, 2]),
            ])

        data = [
            [Paragraph("CONSOMMATION ACTUELLE", self.card_label_style), bar(current_w, colors.HexColor('#ef4444')), Paragraph(f"<b>{current_val:.0f}</b>", self.body_style)],
            [Paragraph("APRÈS TRAVAUX", self.card_label_style), bar(target_w, colors.HexColor('#22c55e')), Paragraph(f"<b>{target_val:.0f}</b>", self.body_style)]
        ]
        t = Table(data, colWidths=[3.5*cm, 6*cm, 1.5*cm])
        t.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        return t

    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = PremiumPDFReport(
            buffer, 
            pagesize=A4, 
            rightMargin=1.5*cm, 
            leftMargin=1.5*cm, 
            topMargin=3.0*cm, 
            bottomMargin=2*cm
        )
        elements = []

        # --- HERO SECTION ---
        elements.append(Spacer(1, -2.2*cm)) # Move into the header area
        elements.append(Paragraph(data.get('address', 'ADRESSE DU BIEN'), self.title_style))
        elements.append(Spacer(1, 1.5*cm))
        
        # Metric Cards Row 1
        card_row1 = [
            [
                self.create_metric_card("Surface", f"{data.get('surface', 0)} m²"),
                self.create_metric_card("Type", data.get('building_type', 'Logement')),
                self.create_metric_card("Construction", data.get('construction_period') or 'N/A')
            ]
        ]
        t_cards1 = Table(card_row1, colWidths=[4.8*cm, 4.8*cm, 4.8*cm])
        elements.append(t_cards1)
        elements.append(Spacer(1, 10))

        # --- ENERGY PERFORMANCE (HERO) ---
        elements.append(Paragraph("Objectif Performance Énergétique", self.section_header_style))
        
        hero_data = [
            [
                self.create_hero_dpe_badge(data.get('new_label', 'G')),
                [
                    Paragraph("VALEUR ESTIMÉE DU GAIN", self.metric_label_style),
                    Paragraph(f"<font size='24' color='#22c55e'><b>+{data.get('latent_gain', 0):,.0f} €</b></font>", self.body_style),
                    Spacer(1, 4),
                    Paragraph(f"Économie : <b>{round(data.get('annual_savings', 0)):,.0f}€/an</b>", self.body_style),
                    Spacer(1, 10),
                    self.create_energy_bar(data.get('initial_cep', 400), data.get('new_cep', 100))
                ]
            ]
        ]
        t_hero = Table(hero_data, colWidths=[3*cm, 12*cm])
        t_hero.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (1,0), (1,0), 20),
        ]))
        elements.append(t_hero)
        
        if data.get('ban_date'):
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(
                f"<b>ALERTE LOCATION :</b> Interdit à la mise en location dès le <u>{data.get('ban_date')}</u>", 
                ParagraphStyle('Alert', parent=self.body_style, textColor=colors.HexColor('#dc2626'), fontSize=9, fontName='Helvetica-Bold', backColor=colors.HexColor('#fee2e2'), borderPadding=6, borderRadius=4)
            ))

        # --- IA NARRATIVE ---
        if data.get('ai_narrative'):
            elements.append(Paragraph("Analyse de l'Expert SPREA", self.section_header_style))
            raw_text = data.get('ai_narrative')
            formatted_text = raw_text.replace("L'Analyse de l'Expert", "<b>L'Analyse</b>").replace("La Stratégie Conseillée", "<b>La Stratégie</b>")
            elements.append(Paragraph(formatted_text, ParagraphStyle('AIStyle', parent=self.body_style, leading=13, fontSize=9.5, backColor=colors.HexColor('#f1f5f9'), borderPadding=10, borderRadius=6)))

        # --- PLAN DE FINANCEMENT ---
        elements.append(Paragraph("Plan de Financement", self.section_header_style))
        
        fin_rows = []
        # Detailed Works
        detailed = data.get('detailed_costs', [])
        for item in detailed:
            name = item.get('name', 'Travaux')
            if item.get('suggested'): name = f"<b>{name}</b> <font color='#2563eb' size='7'>(Conseillé)</font>"
            fin_rows.append([Paragraph(name, self.body_style), Paragraph(f"<b>{item.get('cost', 0):,.0f} €</b>", self.body_style)])
            
        fin_rows.append([HRFlowable(width="100%", thickness=1, color=colors.HexColor('#f1f5f9')), HRFlowable(width="100%", thickness=1, color=colors.HexColor('#f1f5f9'))])
        fin_rows.append([Paragraph("<b>TOTAL TRAVAUX (BRUT)</b>", self.body_style), Paragraph(f"<b>{data.get('total_cost', 0):,.0f} €</b>", self.body_style)])
        
        fin_rows.append([Spacer(1, 5), Spacer(1, 5)])
        fin_rows.append([Paragraph("<b>AIDES & SUBVENTIONS</b>", self.metric_label_style), ""])
        fin_rows.append([Paragraph("MaPrimeRénov'", self.body_style), Paragraph(f"<font color='#22c55e'>- {data.get('subsidies', 0):,.0f} €</font>", self.body_style)])
        
        if data.get('cee_est'):
            fin_rows.append([Paragraph("Primes CEE", self.body_style), Paragraph(f"<font color='#64748b'><i>(À percevoir)</i> {data.get('cee_est', 0):,.0f} €</font>", self.body_style)])
        
        if data.get('tax_benefit'):
            fin_rows.append([Paragraph("Avantage Fiscal", self.body_style), Paragraph(f"<font color='#64748b'><i>(Indirect)</i> {data.get('tax_benefit', 0):,.0f} €</font>", self.body_style)])

        t_fin = Table(fin_rows, colWidths=[12.5*cm, 5.5*cm])
        t_fin.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,-2), 0.1, colors.HexColor('#f1f5f9')),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(t_fin)
        
        # Reste à Charge (Highlight Card)
        elements.append(Spacer(1, 8))
        net_table = [[
            Paragraph("RESTE À CHARGE FINAL", self.metric_label_style), 
            Paragraph(f"{data.get('rest_to_pay', 0):,.0f} €", self.net_cost_style)
        ]]
        t_net = Table(net_table, colWidths=[10*cm, 8*cm])
        t_net.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#eff6ff')),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('TOPPADDING', (0,0), (-1,-1), 12),
            ('LEFTPADDING', (0,0), (-1,-1), 15),
            ('RIGHTPADDING', (0,0), (-1,-1), 15),
            ('ROUNDEDCORNERS', [8, 8, 8, 8]),
        ]))
        elements.append(t_net)

        # Performance Metrics Row
        elements.append(Spacer(1, 10))
        roi_row = [
            [
                self.create_metric_card("Rentabilité Brut", f"{data.get('yield_brut', 0):.1f} %", '#f0fdf4'),
                self.create_metric_card("Payback Travaux", f"{data.get('roi_years', 0)} ans", '#f0f9ff'),
                self.create_metric_card("DPE ADEME", data.get('ademe_dpe_number', 'N/A')[:10], '#f8fafc')
            ]
        ]
        t_roi = Table(roi_row, colWidths=[4.8*cm, 4.8*cm, 4.8*cm])
        elements.append(t_roi)

        # --- FOCUS AIDES (New Page) ---
        if data.get('focus_mpr') or data.get('focus_cee') or data.get('focus_eco_ptz'):
            elements.append(PageBreak())
            elements.append(Paragraph("DÉTAILS DES AIDES FINANCIÈRES", self.section_header_style))
            elements.append(Spacer(1, 10))
            
            if data.get('focus_mpr'):
                elements.append(Paragraph("FOCUS MAPRIMERÉNOV'", ParagraphStyle('FocusTitle', parent=self.body_style, fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#2563eb'), spaceAfter=5)))
                elements.append(Paragraph(data.get('focus_mpr'), self.body_style))
                elements.append(Spacer(1, 12))
            
            if data.get('focus_cee'):
                elements.append(Paragraph("FOCUS PRIMES CEE", ParagraphStyle('FocusTitle', parent=self.body_style, fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#16a34a'), spaceAfter=5)))
                elements.append(Paragraph(data.get('focus_cee'), self.body_style))
                elements.append(Spacer(1, 12))
                
            if data.get('focus_eco_ptz'):
                elements.append(Paragraph("FOCUS ÉCO-PRÊT À TAUX ZÉRO", ParagraphStyle('FocusTitle', parent=self.body_style, fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#3b82f6'), spaceAfter=5)))
                elements.append(Paragraph(data.get('focus_eco_ptz'), self.body_style))
                elements.append(Spacer(1, 12))

        # Footer Legal Note (if it fits)
        elements.append(Spacer(1, 15))
        elements.append(HRFlowable(width="30%", thickness=0.5, color=colors.HexColor('#94a3b8'), hAlign='CENTER'))
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(
            "Ce document est une simulation basée sur la méthode 3CL-2021 et les prix marchés moyens 2024-2025. <br/>"
            "Il ne remplace pas un audit énergétique réglementaire ou un devis d'artisan certifié RGE.",
            ParagraphStyle('Legal', parent=self.body_style, fontSize=7, alignment=1, textColor=colors.HexColor('#64748b'), leading=9)
        ))

        doc.build(elements)
        buffer.seek(0)
        return buffer.read()

pdf_service = PDFReportGenerator()
