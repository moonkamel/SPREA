"""Fictitious minutes of a general meeting (PV d'AG), to try the document
reader end to end without real documents: invented residence, names and
figures.

  python scripts/audit/sample_pv.py out.pdf
"""
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

PAGES = [
    ["PROCÈS-VERBAL DE L'ASSEMBLÉE GÉNÉRALE ORDINAIRE DU 12 MAI 2025",
     "Syndicat des copropriétaires de la Résidence Les Tilleuls, 14 rue des Arts, 59800 Lille. Syndic : Cabinet Exemple Gestion (SAS).",
     "Copropriétaires présents ou représentés : 3 812 / 10 000 tantièmes (14 copropriétaires sur 24 lots principaux).",
     "Résolution 1 – Élection du président de séance : M. Jean Fictif est élu à l'unanimité.",
     "Résolution 2 – Approbation des comptes de l'exercice 2024 : approuvés. Charges de l'exercice : 58 420 €. Montant des impayés de copropriétaires au 31/12/2024 : 11 350 €, dont 8 900 € pour le lot n° 7.",
     "Résolution 3 – Budget prévisionnel 2026 : adopté pour 61 000 €."],
    ["Résolution 4 – Ravalement des façades sur rue et sur cour : devis de l'entreprise Façades du Nord pour 186 400 € TTC, honoraires du syndic 2,5 %. Adoptée à la majorité de l'article 25 (5 230 tantièmes). Appels de fonds : 40 % au 01/01/2026, 30 % au 01/04/2026, 30 % au 01/07/2026.",
     "Résolution 5 – Remplacement de l'ascenseur : devis de 94 000 € TTC. Rejetée faute de majorité (article 25 non atteint, 3 812 tantièmes). Le conseil syndical demande de reporter la question à la prochaine assemblée ; l'ascenseur a connu 9 pannes en 2024.",
     "Résolution 6 – Fonds de travaux (loi ALUR) : maintien de la cotisation à 5 % du budget. Solde du fonds au 31/12/2024 : 17 800 €.",
     "Résolution 7 – Projet de plan pluriannuel de travaux : le syndic présente le projet établi en mars 2025 (toiture 2028 : 120 000 € ; isolation des combles 2027 : 35 000 €). Adoption reportée."],
    ["Résolution 8 – Procédure contre le copropriétaire du lot n° 7 (Mme Anne Exemple) pour recouvrement des charges : autorisation donnée au syndic d'assigner devant le tribunal judiciaire de Lille.",
     "Résolution 9 – Infiltrations en toiture (sinistre déclaré le 03/02/2025 à l'assureur) : expertise en cours.",
     "Résolution 10 – DPE collectif : vote de la réalisation d'un DPE collectif pour 2 400 € TTC, à réaliser avant le 31/12/2025.",
     "Questions diverses : changement de syndic intervenu en 2024 ; plusieurs copropriétaires signalent des nuisances dans la cour.",
     "La séance est levée à 21 h 15. Le président, la secrétaire, le scrutateur."],
]


def main(path: str):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4)
    story = []
    for i, page in enumerate(PAGES):
        for j, line in enumerate(page):
            story += [Paragraph(line, styles["Title" if i == 0 and j == 0 else "BodyText"]), Spacer(1, 8)]
        if i < len(PAGES) - 1:
            story.append(PageBreak())
    doc.build(story)


if __name__ == "__main__":
    main(sys.argv[1])
