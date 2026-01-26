from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from io import BytesIO

class PremiumPDFReport(SimpleDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self.header_color = colors.HexColor('#0f172a')  # Slate 900
        self.accent_color = colors.HexColor('#3b82f6')  # Blue 500

    def beforePage(self):
        self.canv.saveState()
        # Draw a subtle sidebar or top bar accent
        self.canv.setFillColor(self.header_color)
        self.canv.rect(0, A4[1]-1.5*cm, A4[0], 1.5*cm, fill=1, stroke=0)
        
        # Bottom branding
        self.canv.setFont('Helvetica-Bold', 8)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawString(1.5*cm, 0.8*cm, "SPREA - INTELLIGENCE IMMOBILIÈRE")
        self.canv.drawRightString(A4[0]-1.5*cm, 0.8*cm, f"PAGE {self.canv.getPageNumber()}")
        self.canv.restoreState()

class PDFReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'TitleStyle',
            parent=self.styles['Heading1'],
            fontSize=32,
            textColor=colors.HexColor('#ffffff'),
            spaceAfter=2,
            fontName='Helvetica-Bold',
            alignment=0,
            leading=36
        )
        self.subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2563eb'),
            spaceBefore=12,
            spaceAfter=8,
            fontName='Helvetica-Bold',
            textTransform='uppercase',
            letterSpacing=1.2
        )
        self.body_style = ParagraphStyle(
            'BodyStyle',
            parent=self.styles['BodyText'],
            fontSize=10,
            textColor=colors.HexColor('#334155'),
            leading=13
        )
        self.metric_label_style = ParagraphStyle(
            'MetricLabel',
            parent=self.body_style,
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#94a3b8'),
            textTransform='uppercase',
            letterSpacing=0.8
        )
        self.net_cost_style = ParagraphStyle(
            'NetCostStyle',
            parent=self.body_style,
            fontSize=18,
            textColor=colors.HexColor('#2563eb'),
            fontName='Helvetica-Bold',
            alignment=2
        )

    def get_dpe_color(self, label):
        colors_map = {
            'A': '#22c55e', 'B': '#84cc16', 'C': '#eab308', 'D': '#f59e0b', 
            'E': '#f97316', 'F': '#ef4444', 'G': '#b91c1c',
        }
        return colors.HexColor(colors_map.get(label, '#cbd5e1'))

    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = PremiumPDFReport(
            buffer, 
            pagesize=A4, 
            rightMargin=1.5*cm, 
            leftMargin=1.5*cm, 
            topMargin=2.5*cm, 
            bottomMargin=2*cm
        )
        elements = []

        # --- COVER SECTION ---
        elements.append(Spacer(1, -1.0*cm)) # Move up into the dark header
        elements.append(Paragraph(data.get('address', 'N/A'), self.title_style))
        elements.append(Paragraph("SYNTHÈSE DE RÉNOVATION ÉNERGÉTIQUE", ParagraphStyle('SubHeader', parent=self.title_style, fontSize=10, textColor=colors.HexColor('#94a3b8'), fontName='Helvetica')) )
        
        elements.append(Spacer(1, 1*cm))
        
        # Info row (Surface, Year, DPE ID)
        info_row = [
            [Paragraph("SURFACE", self.metric_label_style), Paragraph("CONSTRUCTION", self.metric_label_style), Paragraph("ID PROPRIÉTÉ", self.metric_label_style)],
            [Paragraph(f"<b>{data.get('surface', 0)} m²</b>", self.body_style), Paragraph(f"<b>{data.get('year', 'N/A')}</b>", self.body_style), Paragraph(f"<b>{data.get('ademe_dpe_number', 'N/A')}</b>", self.body_style)]
        ]
        t_info = Table(info_row, colWidths=[6*cm, 6*cm, 6*cm])
        t_info.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        elements.append(t_info)
        
        if data.get('ban_date'):
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(
                f"<b>ALERTE :</b> Location interdite au {data.get('ban_date')} (Loi Climat)", 
                ParagraphStyle('Alert', parent=self.body_style, textColor=colors.red, fontSize=9)
            ))
        
        elements.append(Spacer(1, 15))

        # --- PERFORMANCE SECTION ---
        elements.append(Paragraph("Objectifs Énergétiques", self.subtitle_style))
        
        perf_summary = [
            [
                Paragraph("<b>ACTUEL</b>", self.metric_label_style),
                Paragraph("<b>PROJETÉ</b>", self.metric_label_style),
                Paragraph("<b>ÉCONOMIES</b>", self.metric_label_style)
            ],
            [
                Paragraph(f"<font size='32' color='{self.get_dpe_color(data.get('current_label', 'G'))}'><b>{data.get('current_label', 'G')}</b></font>", self.body_style),
                Paragraph(f"<font size='32' color='{self.get_dpe_color(data.get('new_label', 'G'))}'><b>{data.get('new_label', 'G')}</b></font>", self.body_style),
                Paragraph(f"<font size='32' color='#16a34a'><b>-{round(data.get('annual_savings', 0)):,.0f}€</b></font>", self.body_style)
            ],
            [
                Paragraph(f"{data.get('initial_cep', 0):.1f} kWh/m².an", self.body_style),
                Paragraph(f"{data.get('new_cep', 0):.1f} kWh/m².an", self.body_style),
                Paragraph("/an estimés", ParagraphStyle('Small', parent=self.body_style, fontSize=8))
            ]
        ]
        
        t_perf = Table(perf_summary, colWidths=[6*cm, 6*cm, 6*cm])
        t_perf.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('TOPPADDING', (0,0), (-1,-1), 10),
        ]))
        elements.append(t_perf)
        elements.append(Spacer(1, 15))

        # --- FINANCIAL SECTION (Optimized for Page 1) ---
        elements.append(Paragraph("Plan de Financement Stratégique", self.subtitle_style))
        
        fin_data = []
        # Group items
        if data.get('purchase_price', 0) > 0:
            fin_data.append(["Prix d'Acquisition", f"{data.get('purchase_price', 0):,.0f} €"])
        
        # Compact works
        works_total = data.get('total_cost', 0)
        detailed = data.get('detailed_costs', [])
        for item in detailed:
            name = item.get('name', 'Travaux')
            if item.get('suggested'): name = f"{name} *"
            fin_data.append([Paragraph(name, self.body_style), f"{item.get('cost', 0):,.0f} €"])
            
        fin_data.append([Paragraph("<b>TOTAL TRAVAUX (BRUT)</b>", self.body_style), Paragraph(f"<b>{works_total:,.0f} €</b>", self.body_style)])
        
        # Grants & Deductions
        fin_data.append([Paragraph("Subventions MaPrimeRénov'", self.body_style), Paragraph(f"<font color='#16a34a'>- {data.get('subsidies', 0):,.0f} €</font>", self.body_style)])
        if data.get('cee_est'):
            fin_data.append(["Prime CEE (Estimation)", f"- {data.get('cee_est', 0):,.0f} €"])
        if data.get('tax_benefit'):
            fin_data.append([Paragraph("Gain Fiscal (Déficit Foncier)", self.body_style), Paragraph(f"<font color='#2563eb'>- {data.get('tax_benefit', 0):,.0f} €</font>", self.body_style)])
        
        # Financing
        if data.get('eco_ptz_amount'):
            fin_data.append(["Prêt Éco-PTZ (Taux 0)", f"- {data.get('eco_ptz_amount', 0):,.0f} €"])
        if data.get('pam_amount'):
            fin_data.append(["Prêt Avance Mutation (PAM)", f"- {data.get('pam_amount', 0):,.0f} €"])

        t_fin = Table(fin_data, colWidths=[13*cm, 5*cm])
        t_fin.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,-2), 0.2, colors.HexColor('#e2e8f0')),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(t_fin)
        
        if data.get('has_iti'):
             elements.append(Spacer(1, 4))
             elements.append(Paragraph(
                 "<i>* Attention : L'isolation des murs par l'intérieur (ITI) réduit la surface habitable (~1.5%).</i>", 
                 ParagraphStyle('SmallAlert', parent=self.body_style, fontSize=7, textColor=colors.HexColor('#92400e'))
             ))
        
        # Net Charge Bold Highlight
        elements.append(Spacer(1, 10))
        net_table = [[Paragraph("RESTE À CHARGE NET", self.metric_label_style), Paragraph(f"{data.get('rest_to_pay', 0):,.0f} €", self.net_cost_style)]]
        t_net = Table(net_table, colWidths=[10*cm, 8*cm])
        t_net.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#eff6ff')),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('TOPPADDING', (0,0), (-1,-1), 12),
        ]))
        elements.append(t_net)
        
        elements.append(Spacer(1, 20))

        # --- ROI SECTION (Compact) ---
        elements.append(Paragraph("Performance de l'Investissement", self.subtitle_style))
        
        roi_data = [
            [Paragraph("RENTABILITÉ BRUT", self.metric_label_style), Paragraph("PLUS-VALUE ESTIMÉE", self.metric_label_style), Paragraph("ROI CAPITAL", self.metric_label_style)],
            [
                Paragraph(f"<b>{data.get('yield_brut', 0):.1f} %</b>", self.body_style), 
                Paragraph(f"<b>+ {data.get('latent_gain', 0):,.0f} €</b>", self.body_style), 
                Paragraph(f"<b>{data.get('roi_years', 0)} ans</b>", self.body_style)
            ]
        ]
        if data.get('cashflow'):
             roi_data[0].insert(1, Paragraph("CASHFLOW", self.metric_label_style))
             roi_data[1].insert(1, Paragraph(f"<font color='#16a34a'><b>+ {data.get('cashflow', 0):,.0f} €</b></font>", self.body_style))

        t_roi = Table(roi_data, colWidths=[4.5*cm]*len(roi_data[0]))
        t_roi.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        elements.append(t_roi)

        # Footer
        elements.append(Spacer(1, 40))
        elements.append(Paragraph(
            "SPREA - Intelligence au service de l'Immobilier Durable. <br/>"
            "Document indicatif généré sur la base de la méthode 3CL-2021.",
            ParagraphStyle('Footer', parent=self.body_style, fontSize=7, alignment=1, textColor=colors.gray)
        ))

        doc.build(elements)
        buffer.seek(0)
        return buffer.read()

pdf_service = PDFReportGenerator()
