-- Run only in your trusted PostgreSQL SQL Editor, on this application's database.
-- Replace YOUR_ADMIN_EMAIL in the final SELECT. Do not paste the resulting link
-- into chat, Git or shared logs. It is a one-time credential valid for 30 minutes.
-- This creates a session-local helper, never a public registration endpoint.
CREATE OR REPLACE FUNCTION pg_temp.hq_bootstrap_admin(p_email text, p_origin text)
RETURNS text
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $bootstrap$
DECLARE
    user_id text;
    raw_token text;
BEGIN
    p_email := lower(btrim(p_email));
    p_origin := rtrim(p_origin, '/');
    IF length(p_email) > 254 OR p_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' THEN
        RAISE EXCEPTION 'Replace YOUR_ADMIN_EMAIL with your administrator email';
    END IF;
    IF p_origin !~ '^https://[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$' THEN
        RAISE EXCEPTION 'Use the HTTPS site origin without a path, query or credentials';
    END IF;

    -- Same serialization row as the application's bootstrap/invitation CLI.
    PERFORM 1 FROM public.access_delivery_state WHERE id = 'access' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Apply access/delivery migrations first';
    END IF;
    IF EXISTS (SELECT 1 FROM public.users) THEN
        RAISE EXCEPTION 'Bootstrap refused: accounts already exist; use administrator recovery';
    END IF;

    user_id := gen_random_uuid()::text;
    -- Two cryptographic UUIDv4 values provide over 240 random bits, without pgcrypto.
    raw_token := replace(gen_random_uuid()::text, '-', '') ||
                 replace(gen_random_uuid()::text, '-', '');
    INSERT INTO public.users (id, email, password, role, enabled)
    VALUES (user_id, p_email, '', 'admin', true);
    INSERT INTO public.access_tokens (id, user_id, kind, expires)
    VALUES (encode(sha256(convert_to(raw_token, 'UTF8')), 'hex'), user_id, 'invite',
            (extract(epoch FROM clock_timestamp())::bigint + 1800)::integer);
    INSERT INTO public.audit_logs (action, subject, created_at)
    VALUES ('account.bootstrap', user_id, clock_timestamp());
    RETURN p_origin || '/dashboard#recover=' || raw_token;
END;
$bootstrap$;

-- Edit only the email below. Open the returned setup_link privately.
SELECT pg_temp.hq_bootstrap_admin(
    'YOUR_ADMIN_EMAIL',
    'https://halal-quant.vercel.app'
) AS setup_link;
