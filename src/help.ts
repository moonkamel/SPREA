// Plain-language explanations shown in the help bubbles (<Help topic="..." />).
// Keep them short: two or three sentences a non-specialist can read in a few seconds.

export const HELP = {
    dpe: {
        title: 'DPE',
        text: "Le diagnostic de performance énergétique classe un logement de A (très économe) à G (très énergivore). Il est obligatoire pour vendre ou louer, et ses résultats sont publiés par l'ADEME.",
    },
    dpeNumber: {
        title: 'Numéro de DPE',
        text: "Identifiant à 13 caractères (ex. 2359E1234567A) inscrit en haut du diagnostic. Il permet de retrouver exactement votre logement, utile quand plusieurs DPE existent à la même adresse.",
    },
    multipleDpe: {
        title: 'Plusieurs résultats ?',
        text: "Un immeuble compte souvent un DPE par logement, et un logement peut avoir été diagnostiqué plusieurs fois. Choisissez celui qui correspond à votre surface et au DPE le plus récent.",
    },
    label: {
        title: 'Étiquette énergie',
        text: "La lettre retenue est la moins bonne des deux notes du DPE : la consommation d'énergie (kWh/m²/an) et les émissions de gaz à effet de serre (kg CO₂/m²/an).",
    },
    labelRecomputed: {
        title: "Pourquoi deux étiquettes ?",
        text: "Ce DPE date d'avant juillet 2024 : nous recalculons l'étiquette avec les seuils en vigueur aujourd'hui, plus favorables pour les logements de moins de 40 m². L'étiquette peut donc s'améliorer sans travaux. Une attestation gratuite peut être téléchargée sur le site de l'Observatoire DPE de l'ADEME.",
    },
    consumption: {
        title: 'Consommation (kWh/m²/an)',
        text: "Énergie nécessaire chaque année par m² pour le chauffage, l'eau chaude, la ventilation, l'éclairage et la climatisation, en énergie primaire (celle qui sert à classer le DPE).",
    },
    bill: {
        title: "Facture d'énergie estimée",
        text: "Estimation de la facture annuelle à partir de la consommation du DPE et des prix moyens 2025-2026 de l'énergie, hors abonnement. Votre facture réelle dépend de votre usage (température, présence).",
    },
    climateLaw: {
        title: 'Loi Climat et location',
        text: "Les logements trop énergivores ne peuvent plus être proposés à la location : classe G depuis 2025, F à partir de 2028, E à partir de 2034 (en métropole). L'interdiction vise les nouveaux baux et les renouvellements ; depuis 2022, le loyer des logements F et G ne peut plus être augmenté.",
    },
    heatLoss: {
        title: 'Où part la chaleur ?',
        text: "Estimation de la répartition des pertes de chaleur selon le type de logement, son époque de construction et l'isolation déclarée dans le DPE. Les postes les plus importants sont ceux à traiter en priorité.",
    },
    scenarios: {
        title: 'Deux scénarios',
        text: "Le scénario recommandé contient les travaux que nous conseillons pour atteindre une meilleure classe. Le scénario personnalisé vous permet de composer votre propre bouquet et de comparer les deux.",
    },
    works: {
        title: 'Les travaux',
        text: "Cochez ou décochez les travaux : tous les montants se recalculent instantanément. Les coûts sont des moyennes de marché ajustées à votre région ; seuls des devis d'artisans RGE font foi.",
    },
    profile: {
        title: 'Votre profil',
        text: "Propriétaire occupant : vous habitez le logement. Investisseur : vous le louez ; nous ajoutons alors le rendement, la trésorerie et l'avantage fiscal des travaux.",
    },
    income: {
        title: 'Catégorie de revenus',
        text: "MaPrimeRénov' dépend des revenus du foyer et de son nombre de personnes. Les catégories vont de « très modestes » à « supérieurs ». Si vous ne savez pas, indiquez votre revenu fiscal de référence : nous la calculons pour vous.",
    },
    rfr: {
        title: 'Revenu fiscal de référence',
        text: "Montant indiqué en première page de votre avis d'impôt sur le revenu. Additionnez les revenus fiscaux de toutes les personnes du foyer.",
    },
    siteConstraints: {
        title: 'Contraintes du chantier',
        text: "Un logement en étage sans ascenseur ou en centre-ville dense coûte plus cher à rénover (accès, stationnement des artisans). Facultatif : laissez les valeurs par défaut si vous ne savez pas.",
    },
    tmi: {
        title: 'Tranche marginale d\'imposition',
        text: "Taux d'imposition qui s'applique à la dernière part de vos revenus (0, 11, 30, 41 ou 45 %). Il figure sur votre avis d'impôt et sert à estimer l'économie d'impôt liée aux travaux.",
    },
    cost: {
        title: 'Coût des travaux',
        text: "Estimation TTC des travaux choisis, fourniture et pose comprises, ajustée à votre région et aux contraintes du chantier. Affichée en fourchette : les devis varient selon le bâtiment et l'artisan, seuls des devis fixent le prix réel.",
    },
    mpr: {
        title: "MaPrimeRénov'",
        text: "Principale aide de l'État (Anah). En rénovation d'ampleur (logement classé E, F ou G, au moins 2 classes gagnées et 2 travaux d'isolation), elle couvre 10 à 80 % des travaux selon vos revenus, dans la limite de 30 000 ou 40 000 € HT de dépenses. Hors rénovation d'ampleur, depuis le 1er septembre 2026, seule la pompe à chaleur reste financée « par geste ».",
    },
    pathway: {
        title: "Rénovation d'ampleur",
        text: "Le « parcours accompagné » de MaPrimeRénov' finance les projets qui font gagner au moins 2 classes à un logement classé E, F ou G. Il impose un rendez-vous France Rénov' puis un Accompagnateur Rénov' qui vous suit du diagnostic à la fin du chantier. Une maison ne peut pas y garder un chauffage au gaz ou au fioul.",
    },
    cee: {
        title: "Primes CEE",
        text: "Primes « certificats d'économies d'énergie » versées par les fournisseurs d'énergie. Hors rénovation d'ampleur, ce sont désormais les seules aides pour l'isolation, les fenêtres, la ventilation et le chauffe-eau. Montants indicatifs : ils varient selon l'offre. Elles ne se cumulent pas avec la rénovation d'ampleur, qui les intègre déjà.",
    },
    rest: {
        title: 'Reste à charge',
        text: "Ce que vous payez réellement : coût des travaux moins les aides, en fourchette selon les devis. Il peut être financé sans intérêts par l'Éco-PTZ.",
    },
    ecoPtz: {
        title: 'Éco-prêt à taux zéro',
        text: "Prêt bancaire sans intérêts pour financer le reste à charge : jusqu'à 15 000 € pour un type de travaux, 25 000 € pour deux, 30 000 € pour trois ou plus, remboursable jusqu'à 15 ans (20 ans pour une rénovation d'ampleur).",
    },
    savings: {
        title: 'Économies annuelles',
        text: "Différence entre la facture d'énergie estimée avant et après travaux, aux prix actuels de l'énergie.",
    },
    payback: {
        title: "Retour sur investissement",
        text: "Nombre d'années pour que les économies d'énergie remboursent le reste à charge. Une hausse des prix de l'énergie le raccourcirait.",
    },
    greenValue: {
        title: 'Valeur verte',
        text: "Hausse estimée de la valeur du bien liée au gain de classes énergie. Nous la mesurons sur les ventes réelles : chaque vente des données DVF (DGFiP) est rapprochée du DPE du logement vendu (ADEME), puis l'écart de prix entre classes est calculé dans votre département, à emplacement, surface, époque et date de vente comparables. Il est appliqué au prix au m² des ventes comparables autour du logement. C'est une tendance de marché, pas une garantie.",
    },
    yield: {
        title: 'Rendement brut',
        text: "Loyers annuels divisés par le prix d'achat augmenté du coût des travaux.",
    },
    cashflow: {
        title: 'Trésorerie mensuelle',
        text: "Loyer mensuel moins la mensualité de l'éco-prêt à taux zéro, et d'un prêt bancaire (7 ans à 4,5 %) pour la part du reste à charge qu'il ne couvre pas. Hors charges, taxe foncière et impôts.",
    },
    taxBenefit: {
        title: "Économie d'impôt",
        text: "Pour un bailleur, les travaux d'amélioration sont déductibles des revenus fonciers. Estimation : reste à charge × (votre taux d'imposition + 17,2 % de prélèvements sociaux).",
    },
    report: {
        title: 'Le rapport PDF',
        text: "Document complet à conserver ou à transmettre : état du logement, travaux, plan de financement, économies et analyse rédigée selon votre profil.",
    },
} as const;

export type HelpTopic = keyof typeof HELP;
