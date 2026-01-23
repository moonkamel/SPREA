from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.units import cm
from io import BytesIO

class PDFReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'TitleStyle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=20,
            fontName='Helvetica-Bold'
        )
        self.subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2563eb'),
            spaceBefore=15,
            spaceAfter=10,
            fontName='Helvetica-Bold'
        )
        self.body_style = self.styles['BodyText']

    def get_dpe_color(self, label):
        colors_map = {
            'A': '#31a354', 'B': '#74c476', 'C': '#a1d99b', 'D': '#feb24c', 
            'E': '#fd8d3c', 'F': '#f03b20', 'G': '#bd0026',
        }
        return colors.HexColor(colors_map.get(label, '#cbd5e1'))

    def generate(self, data: dict) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        elements = []

        # Header
        elements.append(Paragraph("SPREA - Synthèse de Rénovation Énergétique", self.title_style))
        elements.append(Paragraph(f"Adresse : {data.get('address', 'N/A')}", self.body_style))
        elements.append(Spacer(1, 10))
        
        # Property Identity
        elements.append(Paragraph("Identité du Bien", self.subtitle_style))
        identity_data = [
            ["Surface habitable", f"{data.get('surface', 0)} m²"],
            ["Année de construction", f"{data.get('year', 'N/A')}"],
            ["N° DPE ADEME", f"{data.get('ademe_dpe_number', 'N/A')}"]
        ]
        t = Table(identity_data, colWidths=[6*cm, 10*cm])
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # Performance Delta
        elements.append(Paragraph("Performance Énergétique Projetée", self.subtitle_style))
        perf_data = [
            ["Indicateur", "État Actuel", "Après Travaux"],
            ["Label DPE", data.get('current_label', 'G'), data.get('new_label', 'G')],
            ["Énergie Prim. (kWh/m².an)", f"{data.get('initial_cep', 0)}", f"{data.get('new_cep', 0)}"],
            ["Émissions GES (kgCO2/m².an)", f"{data.get('ges_value', 0)}", f"{data.get('new_ges', 0)}"]
        ]
        t = Table(perf_data, colWidths=[6*cm, 5*cm, 5*cm])
        current_color = self.get_dpe_color(data.get('current_label', 'G'))
        new_color = self.get_dpe_color(data.get('new_label', 'G'))
        
        t.setStyle(TableStyle([
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('BACKGROUND', (1, 1), (1, 1), current_color),
            ('BACKGROUND', (2, 1), (2, 1), new_color),
            ('TEXTCOLOR', (1, 1), (2, 1), colors.white),
            ('FONTNAME', (1, 1), (2, 1), 'Helvetica-Bold'),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # Financial Plan
        elements.append(Paragraph("Plan de Financement", self.subtitle_style))
        financial_data = [
            ["Investissement Total", f"{data.get('total_cost', 0):,.0f} €"],
            ["Aides d'État (MPR/CEE)", f"{data.get('subsidies', 0) - data.get('local_aid', 0):,.0f} €"],
            ["Aides Locales & Régionales", f"{data.get('local_aid', 0):,.0f} €"],
            ["Reste à charge Net", f"{data.get('rest_to_pay', 0):,.0f} €"]
        ]
        t = Table(financial_data, colWidths=[8*cm, 8*cm])
        t.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 3), (-1, 3), 12),
            ('TEXTCOLOR', (1, 3), (1, 3), colors.HexColor('#2563eb')),
            ('ALIGN', (1, 0), (1, 3), 'RIGHT'),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)

        # Economic Benefits
        elements.append(Paragraph("Bénéfices & Retour sur Investissement", self.subtitle_style))
        benefits_data = [
            ["Plus-value Immobilière (Valeur Verte)", f"+{data.get('latent_gain', 0):,.0f} €"],
            ["Économies d'énergie annuelles", f"{data.get('annual_savings', 0):,.0f} €/an"],
            ["Temps de retour sur investissement", f"{data.get('roi_years', 0)} ans"]
        ]
        t = Table(benefits_data, colWidths=[8*cm, 8*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f9ff')),
            ('ALIGN', (1, 0), (1, 2), 'RIGHT'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.lightblue),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        
        # Footer Disclaimer
        elements.append(Spacer(1, 30))
        disclaimer = "Ce document est une simulation à caractère informatif générée par l'outil SPREA basé sur la méthode 3CL-2021. Elle ne remplace en aucun cas un audit énergétique réglementaire réalisé par un professionnel certifié."
        elements.append(Paragraph(disclaimer, ParagraphStyle('Disclaimer', parent=self.body_style, fontSize=8, textColor=colors.grey, alignment=1)))

        doc.build(elements)
        buffer.seek(0)
        return buffer.read()

pdf_service = PDFReportGenerator()
