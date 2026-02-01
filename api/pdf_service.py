from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.units import cm
from io import BytesIO

class PremiumPDFReport(SimpleDocTemplate):
    def __init__(self, filename, property_address="", **kw):
        super().__init__(filename, **kw)
        self.header_color = colors.HexColor('#0A192F')
        self.accent_color = colors.HexColor('#2ECC71')
        self.property_address = property_address

    def draw_house_icon(self, x, y, size):
        self.canv.setStrokeColor(self.accent_color)
        self.canv.setLineWidth(1.5)
        p = self.canv.beginPath()
        p.moveTo(x, y + size * 0.4)
        p.lineTo(x + size / 2, y + size)
        p.lineTo(x + size, y + size * 0.4)
        p.moveTo(x + size * 0.2, y + size * 0.4)
        p.lineTo(x + size * 0.2, y)
        p.lineTo(x + size * 0.8, y)
        p.lineTo(x + size * 0.8, y + size * 0.4)
        self.canv.drawPath(p, stroke=1, fill=0)

    def beforePage(self):
        self.canv.saveState()
        # Header
        self.canv.setFillColor(self.header_color)
        self.canv.rect(0, A4[1]-3.5*cm, A4[0], 3.5*cm, fill=1, stroke=0)
        
        # Emerald Accent
        self.canv.setFillColor(self.accent_color)
        p = self.canv.beginPath()
        p.moveTo(A4[0], A4[1])
        p.lineTo(A4[0], A4[1]-3.5*cm)
        p.lineTo(A4[0]-6*cm, A4[1])
        self.canv.drawPath(p, fill=1, stroke=0)

        # Centered Branding
        self.canv.setFillColor(colors.white)
        self.canv.setFont('Helvetica-Bold', 26)
        self.canv.drawCentredString(A4[0]/2, A4[1]-1.2*cm, "SPREA")
        
        self.canv.setFont('Helvetica-Bold', 9)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawCentredString(A4[0]/2, A4[1]-1.7*cm, "INTELLIGENT PROPERTY REPORT")
        
        # Address
        self.canv.setFillColor(colors.white)
        self.canv.setFont('Helvetica-Bold', 14)
        self.canv.drawCentredString(A4[0]/2, A4[1]-2.7*cm, str(self.property_address).upper())

        # Icon
        self.draw_house_icon(A4[0]-1.6*cm, A4[1]-1.8*cm, 0.7*cm)
        
        # Footer
        self.canv.setFont('Helvetica-Bold', 7)
        self.canv.setFillColor(colors.HexColor('#94a3b8'))
        self.canv.drawCentredString(A4[0]/2, 0.8*cm, f"S P R E A   |   A N A L Y S E   F I N T E C H   |   PAGE {self.canv.getPageNumber()}")
        self.canv.restoreState()

class PDFReportGenerator:
    def __init__(self):
        self.colors = {
            'navy': colors.HexColor('#0A192F'),
            'emerald': colors.HexColor('#2ECC71'),
            'blue': colors.HexColor('#3B82F6'),
            'slate': colors.HexColor('#7F8C8D'),
            'bg': colors.HexColor('#F8FAFC'),
            'red': colors.HexColor('#E74C3C')
        }
        self.setup_styles()

    def setup_styles(self):
        self.styles = getSampleStyleSheet()
        self.h1 = ParagraphStyle('H1', fontSize=18, textColor=self.colors['navy'], fontName='Helvetica-Bold', alignment=1, spaceAfter=20)
        self.h2 = ParagraphStyle('H2', fontSize=14, textColor=self.colors['navy'], fontName='Helvetica-Bold', alignment=1, spaceBefore=20, spaceAfter=15)
        self.body_cent = ParagraphStyle('BodyC', fontSize=10, textColor=self.colors['navy'], alignment=1, leading=14)
        self.body_left = ParagraphStyle('BodyL', fontSize=10, textColor=self.colors['navy'], alignment=0, leading=14)
        self.label_style = ParagraphStyle('Label', fontSize=7, fontName='Helvetica-Bold', textColor=self.colors['slate'], alignment=1, textTransform='uppercase')
        self.val_style = ParagraphStyle('Val', fontSize=12, fontName='Helvetica-Bold', textColor=self.colors['navy'], alignment=1)
        self.gain_style = ParagraphStyle('Gain', fontSize=26, fontName='Helvetica-Bold', textColor=self.colors['emerald'], alignment=1, leading=30)
        self.focus_title = ParagraphStyle('FocusT', fontSize=11, fontName='Helvetica-Bold', textColor=self.colors['blue'], alignment=1, spaceAfter=8)
        self.focus_body = ParagraphStyle('FocusB', fontSize=10, textColor=self.colors['navy'], alignment=0, leading=15, leftIndent=1.5*cm, rightIndent=1.5*cm)

    def get_dpe_color(self, label):
        m = {'A': '#22c55e', 'B': '#84cc16', 'C': '#2ECC71', 'D': '#facc15', 'E': '#fb923c', 'F': '#f87171', 'G': '#dc2626'}
        return colors.HexColor(m.get(str(label).upper(), '#cbd5e1'))

    def create_card(self, l, v):
        t = Table([[Paragraph(l, self.label_style)], [Paragraph(v, self.val_style)]], colWidths=[2.6*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), self.colors['bg']),
            ('ROUNDEDCORNERS', [8, 8, 8, 8]),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        return t

    def create_bars(self, cur, tar):
        bw = 6*cm
        cw, tw = (min(cur, 500)/500)*bw, (min(tar, 500)/500)*bw
        def b(w, c): return Table([['']], colWidths=[w], rowHeights=[0.35*cm], style=[('BACKGROUND',(0,0),(-1,-1),c),('ROUNDEDCORNERS',[3,3,3,3])])
        data = [[Paragraph("ACTUEL", self.label_style), b(cw, self.colors['red']), Paragraph(f"<b>{cur:.0f}</b>", self.body_cent)],
                [Paragraph("APRÈS", self.label_style), b(tw, self.colors['emerald']), Paragraph(f"<b>{tar:.0f}</b>", self.body_cent)]]
        t = Table(data, colWidths=[2*cm, 6*cm, 1.2*cm])
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
        return t

    def generate(self, data: dict) -> bytes:
        buf = BytesIO()
        addr = data.get('address', '').upper()
        doc = PremiumPDFReport(buf, property_address=addr, pagesize=A4, rightMargin=2.5*cm, leftMargin=2.5*cm, topMargin=4.5*cm, bottomMargin=2.5*cm)
        elements = []

        # P1: DASHBOARD
        elements.append(Spacer(1, 0.5*cm))
        cards = [[self.create_card("Surface", f"{data.get('surface', 0)}m²"),
                  self.create_card("Type", data.get('building_type', 'N/A')[:12]),
                  self.create_card("Année", (data.get('construction_period') or 'N/A')[:10]),
                  self.create_card("Rendement", f"{data.get('yield_brut', 0):.1f}%"),
                  self.create_card("Retour", f"{data.get('roi_years', 0)} ans"),
                  self.create_card("DPE ADEME", data.get('ademe_dpe_number', 'N/A')[-6:])]]
        elements.append(Table(cards, colWidths=[2.65*cm]*6, style=[('ALIGN',(0,0),(-1,-1),'CENTER')]))

        if data.get('ban_date'):
            elements.append(Spacer(1, 15))
            elements.append(Paragraph(f"ALERTE LOCATION : Interdit à la mise en location dès le {data.get('ban_date')}", 
                ParagraphStyle('A', fontSize=10, textColor=colors.white, fontName='Helvetica-Bold', alignment=1, backColor=self.colors['red'], borderPadding=10, borderRadius=8)))

        elements.append(Spacer(1, 25))
        elements.append(Paragraph("Objectif Performance Énergétique", self.h2))
        
        lab = data.get('new_label', 'G')
        badge = Table([[Paragraph(str(lab), ParagraphStyle('B', fontSize=44, textColor=colors.white, fontName='Helvetica-Bold', alignment=1))]], colWidths=[2.8*cm], rowHeights=[2.8*cm])
        badge.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), self.get_dpe_color(lab)), ('ROUNDEDCORNERS', [12, 12, 12, 12]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        
        hero = [[badge, 
                 [Paragraph("VALEUR ESTIMÉE DU GAIN", self.label_style), Spacer(1,2), Paragraph(f"+{data.get('latent_gain', 0):,.0f} €", self.gain_style), Paragraph(f"Économie : <b>{round(data.get('annual_savings', 0)):,.0f}€/an</b>", self.body_cent)],
                 self.create_bars(data.get('initial_cep', 400), data.get('new_cep', 100))]]
        elements.append(Table(hero, colWidths=[3.5*cm, 5.5*cm, 7*cm], style=[('VALIGN',(0,0),(-1,-1),'MIDDLE'), ('ALIGN',(0,0),(-1,-1),'CENTER')]))

        # P2: FINANCE
        elements.append(PageBreak())
        elements.append(Paragraph("Plan de Financement Global", self.h1))
        
        rows = []
        if data.get('purchase_price', 0) > 0:
            rows.append([Paragraph("PRIX D'ACQUISITION DU BIEN", ParagraphStyle('BL', fontSize=10, fontName='Helvetica-Bold')), Paragraph(f"{data.get('purchase_price', 0):,.0f} €", ParagraphStyle('BR', fontSize=10, fontName='Helvetica-Bold', alignment=2))])
        for it in data.get('detailed_costs', []):
            rows.append([Paragraph(it.get('name', 'Travaux'), self.body_left), Paragraph(f"{it.get('cost', 0):,.0f} €", ParagraphStyle('R', alignment=2))])
        
        rows.append([HRFlowable(width="100%", thickness=1.5, color=self.colors['navy']), HRFlowable(width="100%", thickness=1.5, color=self.colors['navy'])])
        rows.append([Paragraph("TOTAL TRAVAUX (BRUT)", ParagraphStyle('BL', fontSize=11, fontName='Helvetica-Bold')), Paragraph(f"{data.get('total_cost', 0):,.0f} €", ParagraphStyle('BR', fontSize=11, fontName='Helvetica-Bold', alignment=2))])
        
        rows.append([Spacer(1, 10), ""])
        rows.append([Paragraph("AIDES & DÉDUCTIONS ESTIMÉES", self.label_style), ""])
        rows.append([Paragraph("MaPrimeRénov'", self.body_left), Paragraph(f"<font color='#2ECC71'>- {data.get('subsidies', 0):,.0f} €</font>", ParagraphStyle('R', alignment=2))])
        if data.get('cee_est'):
            rows.append([Paragraph("Primes CEE (à percevoir)", self.body_left), Paragraph(f"- {data.get('cee_est', 0):,.0f} €", ParagraphStyle('R', alignment=2))])
            
        t_fin = Table(rows, colWidths=[11*cm, 4*cm])
        t_fin.setStyle(TableStyle([('BOTTOMPADDING',(0,0),(-1,-1),8), ('TOPPADDING',(0,0),(-1,-1),8), ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.white, self.colors['bg']])]))
        elements.append(t_fin)
        
        elements.append(Spacer(1, 30))
        res = [[Paragraph("RESTE À CHARGE FINAL", ParagraphStyle('WL', fontSize=11, textColor=colors.white, fontName='Helvetica-Bold', alignment=1)), 
                Paragraph(f"{data.get('rest_to_pay', 0):,.0f} €", ParagraphStyle('WV', fontSize=30, textColor=colors.white, fontName='Helvetica-Bold', alignment=1))]]
        t_res = Table(res, colWidths=[12*cm])
        t_res.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), self.colors['blue']), ('ROUNDEDCORNERS', [12, 12, 12, 12]), ('TOPPADDING', (0,0), (-1,-1), 20), ('BOTTOMPADDING', (0,0), (-1,-1), 20), ('ALIGN', (0,0), (-1,-1), 'CENTER')]))
        elements.append(t_res)

        # P3: FOCUS
        if data.get('focus_mpr') or data.get('focus_cee') or data.get('focus_eco_ptz'):
            elements.append(PageBreak())
            elements.append(Paragraph("Détails des Aides Financières", self.h1))
            elements.append(Spacer(1, 15))
            for k, t in [('focus_mpr', 'MAPRIMERÉNOV'), ('focus_cee', 'PRIMES CEE'), ('focus_eco_ptz', 'ÉCO-PRÊT À TAUX ZÉRO')]:
                if data.get(k):
                    elements.append(Paragraph(f"FOCUS {t}'", self.focus_title))
                    elements.append(Paragraph(data.get(k), self.focus_body))
                    elements.append(Spacer(1, 35))

        elements.append(Spacer(1, 40))
        elements.append(Paragraph("Simulation 3CL-2021. Ce document ne remplace pas un audit réglementaire.", ParagraphStyle('F', fontSize=7, textColor=self.colors['slate'], alignment=1)))

        doc.build(elements)
        buf.seek(0)
        return buf.read()

pdf_service = PDFReportGenerator()
