# Séquence de prospection – agences immobilières

Envoi depuis **contact@sprea.app** via Zoho Mail, expéditeur « L'équipe SPREA » (signature SPREA ajoutée automatiquement).
Rythme : 1er e-mail, puis une relance par semaine (J+7, J+14, J+21), arrêt dès
qu'une agence répond ou demande à ne plus être contactée.

Variables (remplies pour chaque agence) :
- `{agence}` : nom de l'agence ;
- `{ville}` : commune du siège ;
- `{dpe_30j}` : nombre de logements F ou G ayant reçu un DPE dans la commune ces 30 derniers jours (ADEME) ;
- `{lien}` : `https://sprea.app/demo?utm_source=email&utm_medium=prospection&utm_campaign=agences_59`.

Texte brut, sans image : c'est ce qui passe le mieux les filtres anti-spam.

---

## E-mail 1 – J0

**Objet :** {dpe_30j} nouveaux DPE F ou G à {ville} ce mois-ci
*(si le chiffre est inconnu ou inférieur à 3 : « Les propriétaires de passoires de {ville}, avant les autres »)*

> Bonjour,
>
> À {ville}, {dpe_30j} logements classés F ou G ont reçu un nouveau DPE ces 30 derniers jours. Un DPE récent précède souvent une vente ou une mise en location : ce sont autant de propriétaires à contacter avant les autres.
>
> Nous avons créé SPREA pour les agences comme {agence} : chaque matin, les nouveaux DPE de votre secteur sur une carte, un courrier prêt à envoyer au propriétaire, et un dossier chiffré à lui remettre (travaux, aides, valeur avant et après rénovation).
>
> La visite guidée en images, 3 minutes : {lien}
>
> Si c'est utile, nous vous le montrons en 20 minutes sur vos propres rues. Un créneau cette semaine ?
>
> L'équipe SPREA

---

## E-mail 2 – J+7

**Objet :** une passoire en mandat qui ne part pas ?

> Bonjour,
>
> Un complément à notre message de la semaine dernière.
>
> Quand un bien classé F ou G ne se vend pas, c'est souvent parce que les acheteurs imaginent un gouffre. Depuis SPREA, vous générez en deux minutes un dossier acheteur à vos couleurs : programme de travaux, aides, valeur après rénovation appuyée sur les ventes comparables du quartier, loyer possible. L'acheteur ne voit plus une passoire, mais un projet chiffré.
>
> Le même dossier, en version propriétaire, vous sert au premier rendez-vous pour décrocher le mandat de la suivante.
>
> En images : {lien}
>
> L'équipe SPREA

---

## E-mail 3 – J+14

**Objet :** un mandat paie des années d'abonnement

> Bonjour,
>
> Le calcul est simple : sur une vente à 250 000 €, les honoraires dépassent 10 000 € HT. L'abonnement SPREA démarre à 79 € TTC par mois. Un seul mandat signé grâce à un DPE repéré à temps le rembourse plus de dix fois.
>
> Nous vous proposons 20 minutes en visio, sur votre secteur : vous voyez les propriétaires de vos rues et les immeubles de SCI qui risquent de se vendre, puis vous décidez. Répondez simplement avec un créneau.
>
> L'équipe SPREA

---

## E-mail 4 – J+21

**Objet :** nous ne vous relancerons plus

> Bonjour,
>
> Nous ne vous écrirons plus à ce sujet. Si un jour vous voulez voir les nouveaux DPE et les biens à fort potentiel de {ville}, la visite guidée reste ici : {lien}
>
> Bonne continuation,
> L'équipe SPREA

---

## Pied de chaque e-mail (obligatoire)

> SPREA EI, 239b rue du Jardin des Plantes, 59000 Lille. Pour ne plus recevoir nos messages, répondez simplement « STOP ».

## Règles d'envoi

- Uniquement des adresses professionnelles publiées par l'agence elle-même (site de l'agence), jamais les portails d'annonces.
- Toute réponse « STOP » ou demande de retrait : retrait immédiat et définitif de la liste.
- Montée en charge du domaine : 20 envois par jour la 1re semaine, 35 la 2e, puis 50.
- Envoi en semaine, entre 8 h et 10 h.
- Avant chaque envoi quotidien : lecture des réponses de la veille dans la boîte contact@sprea.app ; toute agence qui a répondu (STOP ou autre) sort de la séquence.
- Suivi dans `prospection-suivi.csv` : agence, email, étape (1 à 4), date du dernier envoi, statut (en cours, répondu, STOP, rebond).

## Séquence des conseillers indépendants (iad…)

Envoyée par `scripts/campaign/send_brevo.py` (`advisor_email`) aux adresses des réseaux de conseillers, au prénom quand il est connu, avec les prix au m² de leur commune (pages /prix-m2) quand elle a une page.

1. **« {Prénom}, qui va vendre à {ville} ce mois-ci ? »** : depuis le 11 août, l'appel de prospection suppose l'accord préalable du particulier ; le courrier reste permis. Tout SPREA en trois temps : repérer les vendeurs (SPREA Command, nouveaux DPE, carte des passoires, immeubles de SCI et signaux BODACC, demandes de l'estimateur), les contacter (connaître le propriétaire : parcelle et demande aux impôts fonciers prêtes, courrier avec QR code, demandes de rappel), signer et vendre (avis de valeur, simulateur, dossier acheteur, PV d'AG, fiche copropriété, artisans RGE, rapport). Bouton : visite guidée. Lien : prix au m² de la commune.
2. **« Les propriétaires de {ville} qui demandent à être rappelés »** : l'estimateur gratuit de sprea.app ; les demandes de rappel du secteur sont transmises au conseiller abonné, avec le consentement du propriétaire. Bouton : l'estimateur, commune pré-remplie.
3. **« {Prénom}, le calcul tient en une ligne »** : 79 € TTC par mois contre une commission ; 20 minutes en visio sur ses rues. Bouton : tarifs.
4. **« Nous ne vous relancerons plus »** : les prix de la commune restent en accès libre ; la visite guidée.
