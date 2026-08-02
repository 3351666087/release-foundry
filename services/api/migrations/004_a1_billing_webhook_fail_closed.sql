-- Round 47 payment callback hardening.
-- The provider-event table is the database admission boundary for billing
-- callbacks. A digest or caller-supplied boolean is not provider authenticity.

BEGIN;

CREATE OR REPLACE FUNCTION releasefoundry_reject_unverified_billing_provider_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.signature_verified IS NOT TRUE THEN
    RAISE EXCEPTION 'unverified billing provider event rejected before persistence'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS billing_provider_events_require_verified_signature
  ON billing_provider_events;

CREATE TRIGGER billing_provider_events_require_verified_signature
BEFORE INSERT OR UPDATE OF signature_verified
ON billing_provider_events
FOR EACH ROW
EXECUTE FUNCTION releasefoundry_reject_unverified_billing_provider_event();

COMMIT;
