# Comptes et paiement : mise en service

La simulation reste gratuite et sans compte. Le rapport PDF demande un compte
(lien de connexion par email) et se paie à l'unité, ou est inclus dans
l'abonnement Pro.

## 1. Supabase

1. Créer un projet sur supabase.com.
2. **SQL Editor** : exécuter `supabase/migrations/001_accounts.sql`.
3. **Authentication > URL Configuration** : mettre l'URL du site dans
   *Site URL* et l'ajouter aux *Redirect URLs* (et `http://localhost:5173`
   pour le développement).
4. **Authentication > Emails** : configurer un SMTP (Resend, Brevo…). Le SMTP
   intégré de Supabase est limité à quelques emails par heure, insuffisant
   en production. Traduire le modèle « Magic Link » en français.
5. **Project Settings > API** : récupérer `SUPABASE_URL`, la clé `anon`
   (`SUPABASE_ANON_KEY`) et la clé `service_role`
   (`SUPABASE_SERVICE_ROLE_KEY`, à ne jamais exposer côté navigateur).
   Si le projet utilise encore l'ancien secret JWT partagé, renseigner aussi
   `SUPABASE_JWT_SECRET`.

## 2. Stripe

1. **Catalogue de produits** : créer
   - « Rapport SPREA » : prix unique (ex. 39 €) → `STRIPE_PRICE_REPORT`
   - « SPREA Pro » : prix récurrent mensuel (ex. 49 €) → `STRIPE_PRICE_PRO`
2. **Développeurs > Clés API** : `STRIPE_SECRET_KEY`.
3. **Développeurs > Webhooks** : ajouter l'endpoint
   `https://<votre-site>/api/stripe/webhook` avec les événements
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`

   puis copier le secret de signature dans `STRIPE_WEBHOOK_SECRET`.
4. **Paramètres > Portail client** : activer l'annulation d'abonnement et
   l'historique des factures.
5. **Paramètres > Facturation** : vérifier les mentions légales des factures
   (raison sociale, SIRET, TVA). La TVA n'est pas calculée automatiquement :
   prévoir des prix TTC ou activer Stripe Tax.

## 3. Vercel

Renseigner toutes les variables de `.env.example` dans
**Project Settings > Environment Variables**, avec `PUBLIC_APP_URL` égal à
l'URL publique du site. Commencer avec les clés Stripe de test
(`sk_test_…`), puis passer aux clés live une fois le parcours vérifié.

## Test local du webhook

```
stripe listen --forward-to localhost:8000/api/stripe/webhook
```

La commande affiche un `whsec_…` à utiliser comme `STRIPE_WEBHOOK_SECRET`.
Carte de test : `4242 4242 4242 4242`, date future, CVC quelconque.
