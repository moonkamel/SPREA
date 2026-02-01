import asyncio
import json
import os
import sys

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

try:
    from api.ademe_client import AdemeConnector
    from api.engine import DPECalculator
    from api.ai_service import ai_service
except ImportError:
    from ademe_client import AdemeConnector
    from engine import DPECalculator
    from ai_service import ai_service

async def run_internal_test():
    print("🚀 Démarrage du test interne SPREA API...")
    
    ademe = AdemeConnector()
    engine = DPECalculator()
    
    # 1. Recherche d'un bien réel (Passoire thermique connue ou adresse type)
    address = "43 rue brule maison, Lille"
    print(f"\n🔍 Recherche de l'adresse : {address}")
    
    try:
        results = await ademe.search_by_address(address)
        if not results:
            print("❌ Aucun résultat trouvé pour cette adresse.")
            return
        
        property_data = results[0]
        print(f"✅ Bien trouvé : {property_data.address}")
        print(f"   DPE Actuel : {property_data.etiquette_dpe} ({property_data.consommation_energie} kWh/m².an)")
        print(f"   Surface : {property_data.shab} m²")
        print(f"   Année de construction : {property_data.construction_year}")
        
    except Exception as e:
        print(f"❌ Erreur lors de la recherche ADEME : {e}")
        return

    # 2. Calcul du Baseline Interne
    print("\n📊 Calcul de la situation actuelle...")
    baseline = engine.calculate(property_data)
    print(f"   Déperditions totales : {baseline['total_heat_loss']:.1f} W/K")
    
    # 3. Arbitrage : Recherche de la meilleure stratégie de rénovation (Cible D)
    print("\n💡 Génération de l'arbitrage de rénovation (Objectif Classe D minimum)...")
    strategy = engine.optimize_retrofit(property_data, target_class='D')
    
    if "works" not in strategy:
        print("⚠️ Impossible d'atteindre la cible D avec les scénarios standards.")
        # Essayer au moins quelques travaux
        strategy = engine.simulate_retrofit(property_data, ["isolation_murs_iti", "pompe_a_chaleur_air_eau"], rfr=25000)

    print(f"   Stratégie retenue : {', '.join(strategy.get('works', []))}")
    print(f"   Nouveau DPE : {strategy.get('new_label')} ({strategy.get('new_cep')} kWh/m².an)")
    print(f"   Coût estimé : {strategy.get('total_cost', 0):,.0f} €")
    print(f"   Aides estimées (MPR) : {strategy.get('subsidies', 0):,.0f} €")
    print(f"   Reste à charge : {strategy.get('rest_to_pay', 0):,.0f} €")
    
    # 4. Simulation de l'IA (Expert Narrative)
    print("\n🤖 Consultation de l'expert IA pour l'arbitrage final...")
    
    report_data = {
        "address": property_data.address,
        "current_label": property_data.etiquette_dpe,
        "initial_cep": property_data.consommation_energie,
        "new_label": strategy.get('new_label'),
        "new_cep": strategy.get('new_cep'),
        "rest_to_pay": strategy.get('rest_to_pay'),
        "latent_gain": strategy.get('latent_gain', 15000), # Valeur indicative
        "annual_savings": strategy.get('annual_savings', 1200)
    }
    
    narrative = await ai_service.generate_narrative(report_data, user_profile="investisseur")
    
    print("\n" + "="*50)
    print("📢 RÉSULTATS COMPLETS DE L'ARBITRAGE SPREA")
    print("="*50)
    print(f"\n🏠 BIEN : {property_data.address}")
    print(f"📉 PERFORMANCE : {property_data.etiquette_dpe} ➡️ {strategy.get('new_label')}")
    print(f"💰 FINANCES : Coût {strategy.get('total_cost', 0):,.0f}€ | Aides {strategy.get('subsidies', 0):,.0f}€ | Net {strategy.get('rest_to_pay', 0):,.0f}€")
    print(f"📈 PLUS-VALUE VERTE ESTIMÉE : {strategy.get('latent_gain', 15000):,.0f} €")
    
    print("\n📝 ANALYSE DE L'EXPERT IA :")
    print("-" * 30)
    print(narrative)
    print("-" * 30)
    print("\n✅ Test terminé avec succès.")

if __name__ == "__main__":
    asyncio.run(run_internal_test())
