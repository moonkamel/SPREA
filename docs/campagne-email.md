# Campagne email aux agences : mise en place avec Brevo

Objectif : écrire aux agences et mandataires de Lille et des environs avec
les chiffres réels de leur commune (nouveaux DPE F et G, immeubles de SCI,
signaux de vente), mis à jour chaque lundi automatiquement.

```
Annuaire des entreprises ──► liste des agences (CSV) ──► + emails ──► liste Brevo
                                                                        │
SPREA (ADEME, immeubles, BODACC) ──► chiffres de chaque commune, chaque lundi ──► attributs des contacts
                                                                        │
                                                    Brevo envoie la séquence de 4 emails
```

## Ce qui est légal

La prospection par email d'un professionnel est permise sans accord préalable
si le message concerne son métier (CNIL, prospection B2B), à condition :

- d'indiquer clairement qui écrit (nom, société, adresse) ;
- de mettre un lien de désinscription dans chaque email (Brevo l'ajoute) ;
- de ne plus écrire aux personnes qui s'y opposent (Brevo les bloque) ;
- d'indiquer d'où viennent les coordonnées (pied de l'email ci-dessous).

Ne pas récupérer d'emails sur SeLoger, Leboncoin ou autres portails (leurs
conditions l'interdisent) : site de chaque agence, ou fichier B2B acheté
auprès d'un prestataire conforme au RGPD.

## 1. Le domaine d'envoi (une fois, 30 minutes, puis 3 semaines de chauffe)

1. Acheter un domaine dédié à la prospection, différent du domaine principal
   (exemple : `sprea-immo.fr`), pour ne jamais exposer le domaine du site si
   des emails sont signalés comme indésirables.
2. Brevo > menu > **Expéditeurs, domaines et IP dédiées** > **Domaines** >
   **Ajouter un domaine** : Brevo donne 3 ou 4 enregistrements DNS (code
   Brevo, DKIM, DMARC) à copier chez le registraire du domaine.
3. **Expéditeurs** > **Ajouter** : `tarik@sprea-immo.fr`, nom affiché
   « Tarik – SPREA ». Créer aussi cette boîte chez le registraire pour lire
   les réponses.
4. Chauffe : 30 emails par jour la première semaine, 60 la deuxième, 100 la
   troisième. Ne pas dépasser 150 par jour et par domaine ensuite.

## 2. La liste des agences

1. GitHub > **Actions** > **Campagne email (Brevo)** > **Run workflow** :
   tâche `liste`, départements `59 62`, codes postaux `590 591 595 596 597`
   pour la métropole lilloise (vide pour tout le département).
2. À la fin, télécharger le fichier `agences` (rubrique *Artifacts*).
   Colonnes : agence, dirigeant, adresse, code postal, ville, code INSEE,
   SIREN… et une colonne `email` vide.
3. Remplir la colonne `email` (adresse de contact publiée sur le site de
   l'agence). Commencer par 200 agences pour la vague test.

## 3. Brevo : attributs, liste, import

1. **Contacts** > **Paramètres** > **Attributs** : créer les attributs texte
   `AGENCE`, `DIRIGEANT`, `CODE_INSEE`, `CODE_POSTAL`, `VILLE`.
   (Les attributs `SPREA_…` sont créés automatiquement par le script.)
2. **Contacts** > **Listes** > créer la liste « Agences Lille ». Noter son
   numéro (ID), visible dans la liste des listes.
3. **Importer des contacts** > fichier CSV (séparateur point-virgule) dans
   cette liste, en associant : `email` → EMAIL, `agence` → AGENCE,
   `civilite_nom` → DIRIGEANT, `code_insee` → CODE_INSEE,
   `code_postal` → CODE_POSTAL, `ville` → VILLE. Ignorer les autres colonnes.
   Cocher la case confirmant que ces contacts sont des professionnels
   contactés pour leur activité.
4. Créer une deuxième liste « A répondu » : on y met à la main les agences
   qui répondent, ce qui arrête leur séquence (étape 5).

## 4. Les chiffres de chaque commune, chaque lundi

1. Brevo > menu > **SMTP & API** > **Clés API** > **Générer une clé** (nom :
   « SPREA »). Copier la clé.
2. GitHub > **Settings** > **Secrets and variables** > **Actions** >
   **New repository secret** : `BREVO_API_KEY` = la clé ;
   `BREVO_LIST_ID` = le numéro de la liste « Agences Lille ».
3. **Actions** > **Campagne email (Brevo)** > **Run workflow** avec la tâche
   `chiffres`. Ensuite c'est automatique, chaque lundi à 7 h.
4. Vérifier dans Brevo, sur un contact, les attributs `SPREA_ACCROCHE`
   (la phrase d'accroche), `SPREA_DPE_30J`, `SPREA_IMMEUBLES`,
   `SPREA_SIGNAUX`, `SPREA_LIEN`.

Exemple de `SPREA_ACCROCHE` : « À Lambersart, 23 logements classés F ou G
ont reçu un nouveau DPE ces 30 derniers jours : autant de propriétaires qui
préparent souvent une vente ou une location, et 4 immeubles entiers
appartiennent à une SCI ou une société, dont 1 avec un signal de vente au
BODACC (dissolution, liquidation…). »

## 5. La séquence (Brevo > Automatisations)

**Automatisations** > **Créer un scénario** > *Scénario personnalisé* :

- Déclencheur : « Contact ajouté à une liste » = Agences Lille.
- Email 1 → attendre 3 jours → Email 2 → attendre 5 jours → Email 3 →
  attendre 7 jours → Email 4.
- Paramètres du scénario > **Critères de sortie** : le contact est ajouté à
  la liste « A répondu », ou se désinscrit.
- Envoi en semaine, entre 8 h et 10 h (paramètre « Heures d'envoi »).

Les emails : éditeur **texte simple** (pas de mise en page, pas d'image),
expéditeur `tarik@sprea-immo.fr`, suivi des clics activé. Les variables
`{{ contact.… }}` sont remplacées par Brevo pour chaque agence.

---

**Email 1 – J0**

Objet : {{ contact.SPREA_DPE_30J }} nouveaux DPE F ou G à {{ contact.SPREA_VILLE }} ce mois-ci

> Bonjour,
>
> {{ contact.SPREA_ACCROCHE }}
>
> Je suis Tarik, ancien de l'immobilier lillois. J'ai créé SPREA pour que
> les agences voient ces propriétaires avant les autres : chaque matin, les
> DPE publiés la veille dans votre secteur, sur une carte, avec un courrier
> prêt à envoyer et une estimation avant / après travaux à leur remettre.
>
> La visite guidée en images (3 minutes) : {{ contact.SPREA_LIEN }}
>
> Si c'est utile pour {{ contact.AGENCE | default : "votre agence" }}, je
> vous le montre en 20 minutes sur vos propres rues.
>
> Tarik
> SPREA – 06 XX XX XX XX

**Email 2 – J3**

Objet : les immeubles de SCI qui vont se vendre à {{ contact.SPREA_VILLE }}

> Bonjour,
>
> Un complément à mon message : SPREA repère aussi les immeubles entiers
> détenus par une SCI dans votre secteur ({{ contact.SPREA_IMMEUBLES }} à
> {{ contact.SPREA_VILLE }}), avec la société propriétaire et ses gérants.
>
> Chaque semaine, nous lisons le BODACC pour chacune de ces sociétés :
> dissolution, liquidation, changement de gérant. Quand une SCI va vendre,
> vous le savez, et l'IA vous dit à qui vous adresser (gérant, liquidateur,
> notaire).
>
> Autre gain de temps : déposez les PV d'AG d'une copropriété, l'IA en sort
> en deux minutes les travaux votés, les appels de fonds et les procédures,
> avec une synthèse PDF à vos couleurs pour l'acheteur.
>
> Les deux en images : {{ contact.SPREA_LIEN }}
>
> Tarik

**Email 3 – J8**

Objet : un mandat = des années d'abonnement

> Bonjour,
>
> Le calcul que font les agences qui utilisent SPREA : sur une vente à
> 250 000 €, les honoraires dépassent 10 000 € HT. L'abonnement Solo coûte
> 79 € TTC par mois. Un seul mandat signé grâce à un DPE repéré à temps ou à
> un immeuble de SCI paie plus de dix ans d'abonnement.
>
> Je vous propose 20 minutes en visio, sur votre secteur : vous voyez les
> propriétaires de vos rues, et vous décidez ensuite. Répondez simplement
> avec un créneau qui vous arrange.
>
> Tarik

**Email 4 – J15**

Objet : je ne vous relance plus

> Bonjour,
>
> Je ne vous écrirai plus à ce sujet. Si un jour vous voulez voir les
> nouveaux DPE et les immeubles de SCI de {{ contact.SPREA_VILLE }}, la
> visite guidée reste ici : {{ contact.SPREA_LIEN }}
>
> Bonne continuation,
> Tarik

---

**Pied de chaque email** (à mettre dans le modèle) :

> SPREA – [raison sociale], [adresse]. Vous recevez ce message car votre
> agence est référencée comme agence immobilière dans l'Annuaire des
> entreprises (données publiques INSEE / RNE). Pour ne plus recevoir nos
> emails : {{ unsubscribe }}

## 6. Mesurer et ajuster

- Les liens portent `utm_campaign=agences_59` : les visites venant de la
  campagne sont identifiables.
- Objectifs de la vague test (200 agences) : 40 % d'ouvertures (indicatif,
  Apple masque une partie des ouvertures), 3 à 5 % de réponses, 1 à 3 démos.
- Les agences qui cliquent sans répondre : un appel deux jours après, en
  partant des chiffres de leur commune.
- Si les réponses sont rares, changer l'objet de l'email 1 en premier
  (c'est lui qui décide de l'ouverture), puis la proposition de l'email 3.
- Au-delà de la métropole : Roubaix-Tourcoing, Villeneuve-d'Ascq, puis Lens,
  Douai, Arras et Valenciennes, une liste Brevo par zone.
