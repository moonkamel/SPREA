import sys
import os
# Add the current directory to path so we can import api modules
sys.path.append(os.getcwd())

from api.pdf_service import pdf_service

data = {
    'address': '43 RUE BRULE MAISON',
    'surface': 28.1,
    'building_type': 'appartement',
    'construction_period': 'avant 1948',
    'yield_brut': 7.7,
    'roi_years': 2,
    'ademe_dpe_number': '2359E05617',
    'ban_date': '01/01/2034',
    'new_label': 'C',
    'latent_gain': 11380,
    'annual_savings': 993,
    'initial_cep': 407,
    'new_cep': 252,
    'detailed_costs': [
        {'name': 'ITI (Murs Intérieurs)', 'cost': 4978},
        {'name': 'Ventilation (VMC)', 'cost': 1519},
        {'name': 'Frais de Stationnement', 'cost': 150}
    ],
    'total_cost': 6647,
    'subsidies': 2991,
    'cee_est': 1600,
    'rest_to_pay': 3656,
    'focus_mpr': "MaPrimeRénov' est l’aide principale de l’État pour la rénovation énergétique. Pour être éligible, le logement doit être construit depuis plus de 15 ans.",
    'focus_cee': "Les Certificats d’Économie d’Énergie sont financés par les 'pollueurs-payeurs'. Cette prime est cumulable avec MaPrimeRénov'."
}

try:
    pdf_bytes = pdf_service.generate(data)
    with open('test_output.pdf', 'wb') as f:
        f.write(pdf_bytes)
    print("PDF generated successfully: test_output.pdf")
except Exception as e:
    print(f"Error during PDF generation: {e}")
    import traceback
    traceback.print_exc()
