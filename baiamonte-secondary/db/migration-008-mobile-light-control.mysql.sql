ALTER TABLE mobile_session_capabilities
    DROP CONSTRAINT mobile_session_capability_name_ck,
    ADD CONSTRAINT mobile_session_capability_name_ck
    CHECK (capability IN ('intake.submit','light.control'));
