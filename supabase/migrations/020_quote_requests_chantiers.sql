-- Requests left on /trouver-des-chantiers (building firms) share the quote requests table.
alter table public.quote_requests drop constraint if exists quote_requests_offer_check;
alter table public.quote_requests add constraint quote_requests_offer_check
    check (offer in ('agence', 'reseau', 'chantier_essai', 'chantier_pack', 'chantier_zone'));
