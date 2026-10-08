-- Daily purges matching the retention periods of the privacy policy:
-- callback requests 3 years after they were left, purchase archive 5 years
-- after the account deletion.

create extension if not exists pg_cron with schema pg_catalog;

select cron.schedule('purge-old-leads', '17 3 * * *',
    $$delete from public.leads where created_at < now() - interval '3 years'$$);

select cron.schedule('purge-purchase-archive', '27 3 * * *',
    $$delete from public.purchase_archive where account_deleted_at < now() - interval '5 years'$$);
