from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.units import cm
from io import BytesIO

class PremiumPDFReport(SimpleDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self.header_color = colors.HexColor('#0f172a')  # Slate 900
        self.accent_color = colors.HexColor('#2563eb')  # Blue 600

    def beforePage(self):
        self.canv.saveState()
        # Top Bar (Header Background)
        self.canv.setFillColor(self.header_color)
        self.canv.rect(0, A4[1]-2.2*cm, A4[0], 2.2*cm, fill=1, stroke=0)
        
        # Logo Text in Header
        self.canv.setFillColor(colors.white)
        self.canv.setFont('Helvetica-Bold', 18)
        self.canv.drawString(1.5*cm, A4[1]-1.4*cm, "SPREA")
        self.canv.setFont('Helvetica', 8)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawString(4.0*cm, A4[1]-1.35*cm, "INTELLIGENT PROPERTY REPORT")
        
        # Bottom branding
        self.canv.setFont('Helvetica-Bold', 8)
        self.canv.setFillColor(colors.HexColor('#cbd5e1'))
        self.canv.drawString(1.5*cm, 0.8*cm, "SPREA - ANALYSE DE RÉNOVATION ÉNERGÉTIQUE")
        self.canv.drawRightString(A4[0]-1.5*cm, 0.8*cm, f"PAGE {self.canv.getPageNumber()}")
        
        # Decorative accent line at bottom
        self.canv.setStrokeColor(self.accent_color)
        self.canv.setLineWidth(2)
        self.canv.line(1.5*cm, 1.2*cm, 3.5*cm, 1.2*cm)
        
        self.canv.restoreState()

class PDFReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'TitleStyle',
            parent=self.styles['Heading1'],
            fontSize=26,
            textColor=colors.white,
            spaceAfter=2,
            fontName='Helvetica-Bold',
            alignment=0,
            leading=30
        )
        self.section_header_style = ParagraphStyle(
            'SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1e293b'), # Slate 800
            spaceBefore=20,
            spaceAfter=12,
            fontName='Helvetica-Bold',
            borderPadding=(0, 0, 8, 0),
            alignment=0
        )
        self.body_style = ParagraphStyle(
            'BodyStyle',
            parent=self.styles['BodyText'],
            fontSize=10,
            textColor=colors.HexColor('#475569'), # Slate 600
            leading=14
        )
        self.metric_label_style = ParagraphStyle(
            'MetricLabel',
            parent=self.body_style,
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#94a3b8'),
            textTransform='uppercase',
            letterSpacing=1.0
        )
        self.badge_style = ParagraphStyle(
            'BadgeText',
            parent=self.body_style,
            fontSize=22,
            textColor=colors.white,
            fontName='Helvetica-Bold',
            alignment=1,
            leading=24
        )
        self.net_cost_style = ParagraphStyle(
            'NetCostStyle',
            parent=self.body_style,
            fontSize=20,
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

    def create_dpe_badge(self, label):
        """Creates a small badge representation for DPE labels."""
        color = self.get_dpe_color(label)
        data = [[Paragraph(str(label).upper(), self.badge_style)]]
        t = Table(data, colWidths=[1.4*cm], rowHeights=[1.4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), color),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROUNDEDCORNERS', [4, 4, 4, 4]),
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

        # --- COVER / ADDRESS SECTION ---
        elements.append(Spacer(1, -2.1*cm)) # Move into the header area
        elements.append(Paragraph(data.get('address', 'ADRESSE DU BIEN'), self.title_style))
        elements.append(Spacer(1, 1.8*cm))
        
        # Property Details Row
        details = [
            [
                Paragraph("TYPE DE BÂTIMENT", self.metric_label_style),
                Paragraph("SURFACE HABITABLE", self.metric_label_style),
                Paragraph("PÉRIODE DE CONSTRUCTION", self.metric_label_style),
                Paragraph("NUMÉRO DPE (ADEME)", self.metric_label_style)
            ],
            [
                Paragraph(f"<b>{data.get('building_type', 'Logement')}</b>", self.body_style),
                Paragraph(f"<b>{data.get('surface', 0)} m²</b>", self.body_style),
                Paragraph(f"<b>{data.get('construction_period') or data.get('year') or 'N/A'}</b>", self.body_style),
                Paragraph(f"<b>{data.get('ademe_dpe_number', 'N/A')}</b>", self.body_style)
            ]
        ]
        t_details = Table(details, colWidths=[4.5*cm]*4)
        t_details.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('TOPPADDING', (0,1), (-1,1), 2),
            ('BOTTOMPADDING', (0,0), (-1,0), 0),
        ]))
        elements.append(t_details)
        
        if data.get('ban_date'):
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(
                f"<b>ALERTE LOCATION :</b> Interdit à la mise en location dès le <u>{data.get('ban_date')}</u>", 
                ParagraphStyle('Alert', parent=self.body_style, textColor=colors.HexColor('#dc2626'), fontSize=9, fontName='Helvetica-Bold')
            ))
        
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceBefore=10, spaceAfter=10))

        # --- IA NARRATIVE SECTION ---
        if data.get('ai_narrative'):
            elements.append(Paragraph("ANALYSE DE NOTRE EXPERT IA", self.section_header_style))
            # Format the narrative text (it might have "L'Analyse" and "La Stratégie" headers)
            raw_text = data.get('ai_narrative')
            # Simple bolding for common headers from prompt
            formatted_text = raw_text.replace("L'Analyse de l'Expert", "<b>L'Analyse de l'Expert</b>").replace("La Stratégie Conseillée", "<b>La Stratégie Conseillée</b>")
            
            elements.append(Paragraph(formatted_text, ParagraphStyle('AIStyle', parent=self.body_style, leading=16, fontSize=11, backColor=colors.HexColor('#f8fafc'), borderPadding=10, borderRadius=8)))
            elements.append(Spacer(1, 15))

        # --- OBJECTIFS ÉNERGÉTIQUES ---
        elements.append(Paragraph("OBJECTIFS ÉNERGÉTIQUES", self.section_header_style))
        
        perf_data = [
            [
                Paragraph("SITUATION ACTUELLE", self.metric_label_style),
                Spacer(1, 1),
                Paragraph("APRÈS TRAVAUX", self.metric_label_style),
                Spacer(1, 1),
                Paragraph("GAIN ESTIMÉ", self.metric_label_style)
            ],
            [
                self.create_dpe_badge(data.get('current_label', 'G')),
                Paragraph("<font size='20'>➔</font>", ParagraphStyle('Arrow', parent=self.body_style, alignment=1, textColor=colors.HexColor('#94a3b8'))),
                self.create_dpe_badge(data.get('new_label', 'G')),
                Spacer(1, 1),
                Paragraph(f"<font color='#16a34a' size='24'><b>-{round(data.get('annual_savings', 0)):,.0f}€/an</b></font>", ParagraphStyle('Gain', parent=self.body_style, alignment=2))
            ],
            [
                Paragraph(f"<b>{data.get('initial_cep', 0):.1f}</b> kWh/m².an", self.body_style),
                Spacer(1, 1),
                Paragraph(f"<b>{data.get('new_cep', 0):.1f}</b> kWh/m².an", self.body_style),
                Spacer(1, 1),
                Paragraph("Économie d'énergie annuelle", ParagraphStyle('Small', parent=self.body_style, fontSize=8, alignment=2))
            ]
        ]
        
        t_perf = Table(perf_data, colWidths=[2.5*cm, 1.5*cm, 2.5*cm, 4.5*cm, 7.0*cm])
        t_perf.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('SPAN', (4,0), (4,0)), # Gain Title area
            ('SPAN', (4,1), (4,1)), # Gain Value
            ('SPAN', (4,2), (4,2)), # Gain Label
        ]))
        elements.append(t_perf)

        # --- PLAN DE FINANCEMENT ---
        elements.append(Paragraph("PLAN DE FINANCEMENT STRATÉGIQUE", self.section_header_style))
        
        fin_rows = []
        if data.get('purchase_price', 0) > 0:
            fin_rows.append([Paragraph("<b>Prix d'Acquisition du bien</b>", self.body_style), Paragraph(f"<b>{data.get('purchase_price', 0):,.0f} €</b>", self.body_style)])
            fin_rows.append([Spacer(1, 5), Spacer(1, 5)])

        # Detailed Works
        detailed = data.get('detailed_costs', [])
        for item in detailed:
            name = item.get('name', 'Travaux')
            if item.get('suggested'): name = f"{name} <font color='#2563eb' size='8'>(Conseillé)</font>"
            fin_rows.append([Paragraph(name, self.body_style), f"{item.get('cost', 0):,.0f} €"])
            
        # Totals and Grants
        fin_rows.append([HRFlowable(width="100%", thickness=1, color=colors.HexColor('#f1f5f9')), HRFlowable(width="100%", thickness=1, color=colors.HexColor('#f1f5f9'))])
        fin_rows.append([Paragraph("<b>TOTAL TRAVAUX (BRUT)</b>", self.body_style), Paragraph(f"<b>{data.get('total_cost', 0):,.0f} €</b>", self.body_style)])
        
        fin_rows.append([Paragraph("MaPrimeRénov' (Estimation)", self.body_style), Paragraph(f"<font color='#16a34a'>- {data.get('subsidies', 0):,.0f} €</font>", self.body_style)])
        if data.get('cee_est'):
            fin_rows.append([Paragraph("Certificats Économie Énergie (CEE)", self.body_style), Paragraph(f"<font color='#16a34a'>- {data.get('cee_est', 0):,.0f} €</font>", self.body_style)])
        if data.get('tax_benefit'):
            fin_rows.append([Paragraph("Gain Fiscal (Déficit Foncier)", self.body_style), Paragraph(f"<font color='#2563eb'>- {data.get('tax_benefit', 0):,.0f} €</font>", self.body_style)])
        
        # Financing
        if data.get('eco_ptz_amount'):
            fin_rows.append([Paragraph("Éco-Prêt à Taux Zéro (Eco-PTZ)", self.body_style), Paragraph(f"- {data.get('eco_ptz_amount', 0):,.0f} €", self.body_style)])

        t_fin = Table(fin_rows, colWidths=[13*cm, 5*cm])
        t_fin.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,-2), 0.1, colors.HexColor('#f1f5f9')),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(t_fin)
        
        # Net Charge Highlight
        elements.append(Spacer(1, 10))
        net_table = [[Paragraph("RESTE À CHARGE NET", self.metric_label_style), Paragraph(f"{data.get('rest_to_pay', 0):,.0f} €", self.net_cost_style)]]
        t_net = Table(net_table, colWidths=[11*cm, 7*cm])
        t_net.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#eff6ff')),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 14),
            ('TOPPADDING', (0,0), (-1,-1), 14),
            ('LINEBELOW', (0,0), (-1,-1), 2, colors.HexColor('#2563eb')),
        ]))
        elements.append(t_net)
        
        if data.get('has_iti'):
             elements.append(Spacer(1, 8))
             elements.append(Paragraph(
                 "<i>* Note : L'isolation par l'intérieur (ITI) génère une perte d'environ 1.5% de surface Carrez.</i>", 
                 ParagraphStyle('SmallAlert', parent=self.body_style, fontSize=7, textColor=colors.HexColor('#92400e'), alignment=1)
             ))

        # --- PERFORMANCE DE L'INVESTISSEMENT ---
        elements.append(Paragraph("PERFORMANCE DE L'INVESTISSEMENT", self.section_header_style))
        
        roi_cells = [
            [Paragraph("RENTABILITÉ BRUT", self.metric_label_style), Paragraph("PLUS-VALUE ESTIMÉE", self.metric_label_style), Paragraph("PAYBACK TRAVAUX", self.metric_label_style)],
            [
                Paragraph(f"<font size='18'><b>{data.get('yield_brut', 0):.1f} %</b></font>", self.body_style), 
                Paragraph(f"<font size='18' color='#16a34a'><b>+ {data.get('latent_gain', 0):,.0f} €</b></font>", self.body_style), 
                Paragraph(f"<font size='18'><b>{data.get('roi_years', 0)} ans</b></font>", self.body_style)
            ]
        ]
        
        t_roi = Table(roi_cells, colWidths=[6*cm]*3)
        t_roi.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,0), 4),
        ]))
        elements.append(t_roi)

        # Footer Legal Note
        elements.append(Spacer(1, 40))
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
