ALTER TABLE water_deliveries
  ADD COLUMN reported_by_username VARCHAR(190) NULL AFTER provider_person_entity,
  ADD COLUMN reported_at DATETIME(6) NULL AFTER reported_by_username,
  ADD COLUMN report_notes TEXT NULL AFTER reported_at,
  ADD COLUMN declared_amount_eur DECIMAL(12,2) NULL AFTER report_notes,
  ADD KEY ix_water_delivery_claim_match (estate_id,provider_person_entity,status,completed_at);
