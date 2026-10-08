# Comptes et paiement : mise en service

La simulation reste gratuite et sans compte. Le rapport PDF demande un compte
(lien de connexion par email) et se paie à l'unité, ou est inclus dans
l'abonnement Pro.

## 1. Supabase

1. Créer un projet sur supabase.com.
2. **SQL Editor** : exécuter les fichiers de `supabase/migrations/` dans l'ordre
   (`001_accounts.sql`, `002_terms_acceptance.sql`, `003_purchase_archive.sql`).
   La table `purchase_archive` garde 5 ans une trace des achats des comptes
   supprimés : planifier sa purge (requête en tête du fichier, via pg_cron).
3. **Authentication > URL Configuration** : mettre l'URL du site dans
   *Site URL* et l'ajouter aux *Redirect URLs* (et `http://localhost:5173`
   pour le développement).
4. **Authentication > Emails** : configurer un SMTP (Resend, Brevo…). Le SMTP
   intégré de Supabase est limité à quelques emails par heure, insuffisant
   en production. Traduire le modèle « Magic Link » en français.
5. **Project Settings > Data API** : récupérer l'URL du projet (`SUPABASE_URL`).
   **Project Settings > API Keys** : la clé publishable `sb_publishable_…`
   (ou l'ancienne clé `anon`) va dans `SUPABASE_ANON_KEY`, la clé secrète
   `sb_secret_…` (ou l'ancienne `service_role`) dans
   `SUPABASE_SERVICE_ROLE_KEY`, à ne jamais exposer côté navigateur.
   Les deux générations de clés fonctionnent. `SUPABASE_JWT_SECRET` n'est utile
   que si le projet signe encore ses jetons avec l'ancien secret partagé.

## 2. Stripe

Commencer en mode test (clés `sk_test_…`), puis refaire ces étapes en mode live.

1. **Catalogue de produits** : créer
   - « Rapport SPREA » : prix unique de 39 € → `STRIPE_PRICE_REPORT`
   - « SPREA Pro » : prix récurrent mensuel de 49 € → `STRIPE_PRICE_PRO`

   Pour chaque prix, choisir **« Taxes incluses »** (le site affiche des prix
   TTC) et, sur le produit, le code fiscal « Services fournis par voie
   électronique » (`txcd_10000000`).
2. **Développeurs > Clés API** : `STRIPE_SECRET_KEY`. La clé publique
   (`pk_…`) n'est pas utilisée : le paiement se fait sur la page Stripe Checkout.
3. **Développeurs > Webhooks** : ajouter l'endpoint
   `https://sprea.vercel.app/api/stripe/webhook` avec les événements
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`

   puis copier le secret de signature dans `STRIPE_WEBHOOK_SECRET`.
4. **Paramètres > Portail client** : activer l'annulation d'abonnement et
   l'historique des factures.
5. **Paramètres > Facturation > Factures** : renseigner raison sociale,
   adresse, SIRET et numéro de TVA (ou la mention de franchise en base), et
   activer l'envoi des factures et reçus par email.
6. **Paramètres > Facturation > Abonnements et emails** : activer les
   relances automatiques (Smart Retries) et les emails en cas d'échec de
   paiement ou de carte expirée.
7. **TVA (Stripe Tax)**, si la société est assujettie à la TVA :
   - Paramètres > Taxes : adresse d'origine, puis ajouter l'immatriculation
     **France** ;
   - mettre `STRIPE_AUTOMATIC_TAX=true` dans Vercel.

   Stripe calcule alors la TVA selon l'adresse du client, et les
   professionnels peuvent saisir leur numéro de TVA (affiché sur la facture).
   Stripe Tax est facturé 0,5 % par transaction. En franchise en base de TVA
   (micro-entreprise), laisser `STRIPE_AUTOMATIC_TAX` vide.

## 3. Vercel

Renseigner toutes les variables de `.env.example` dans
**Project Settings > Environment Variables**, avec `PUBLIC_APP_URL` égal à
l'URL publique du site (`https://sprea.vercel.app`). Commencer avec les clés Stripe de test
(`sk_test_…`), puis passer aux clés live une fois le parcours vérifié.

## Test local du webhook

```
stripe listen --forward-to localhost:8000/api/stripe/webhook
```

La commande affiche un `whsec_…` à utiliser comme `STRIPE_WEBHOOK_SECRET`.
Carte de test : `4242 4242 4242 4242`, date future, CVC quelconque.

## 4. Informations légales, CGV et confidentialité

Avant toute vente, compléter `src/legal.ts` : raison sociale, forme juridique,
adresse, SIREN/RCS, TVA, téléphone, email de contact, directeur de la
publication, médiateur de la consommation (adhésion obligatoire pour vendre
aux particuliers), tribunal compétent et région du projet Supabase. Vérifier
l'adresse de Vercel sur vercel.com/legal. Ces informations alimentent les
CGV (`/cgv`), les mentions légales (`/mentions-legales`) et la politique de
confidentialité (`/confidentialite`).
Tant qu'une valeur reste entre crochets, un bandeau l'indique sur la page CGV.

Les CGV (`src/pages/Cgv.tsx`) sont un modèle adapté au service : à faire
relire par un juriste. À chaque modification, changer la date de version
dans `src/legal.ts` (`CGV_VERSION`) et dans `api/accounts.py`
(`TERMS_VERSION`) : chaque achat enregistre la version acceptée.

La politique de confidentialité (`src/pages/Confidentialite.tsx`) décrit les
traitements tels qu'ils sont codés : la mettre à jour (et sa date) à chaque
nouveau prestataire ou nouvelle donnée collectée. Utiliser une clé Gemini
d'un projet avec facturation activée : sur l'offre gratuite, Google peut
utiliser les requêtes pour améliorer ses produits.
