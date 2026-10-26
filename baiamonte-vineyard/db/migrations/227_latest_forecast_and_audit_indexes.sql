-- Follow-up profiling after migration 226 showed that treatment planning was
-- reading every GDD revision for the current season, and that treatment audit
-- history used a non-sargable YEAR() predicate. These indexes serve the revised
-- latest-per-variety and bounded-date queries.
ALTER TABLE gdd_forecasts
  ADD INDEX IF NOT EXISTS ix_gdd_estate_season_variety_computed (estate_id,season_id,variety_id,computed_at);

ALTER TABLE audit_events
  ADD INDEX IF NOT EXISTS ix_audit_estate_entity_time (estate_id,entity_type,occurred_at);
