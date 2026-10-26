-- Live endpoint profiling on 2026-10-26 identified three repeatable hot paths:
-- the processing log ordered by estate/time, current integration failures with
-- a newer-event anti-join, and current-season GDD forecasts. Keep these indexes
-- aligned to those measured predicates rather than indexing every foreign key.
ALTER TABLE integration_events
  ADD INDEX IF NOT EXISTS ix_integration_estate_time (estate_id,occurred_at,id),
  ADD INDEX IF NOT EXISTS ix_integration_estate_status_time (estate_id,status,occurred_at,id),
  ADD INDEX IF NOT EXISTS ix_integration_estate_stream_time (estate_id,integration_name,event_type,occurred_at,id);

ALTER TABLE gdd_forecasts
  ADD INDEX IF NOT EXISTS ix_gdd_estate_season_dates (estate_id,season_id,final_forecast_date,predicted_date),
  ADD INDEX IF NOT EXISTS ix_gdd_estate_variety_computed (estate_id,variety_id,computed_at);
