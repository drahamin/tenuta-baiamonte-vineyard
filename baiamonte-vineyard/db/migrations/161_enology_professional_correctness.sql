-- Professional enology correctness: store only distinct prediction inputs.
ALTER TABLE enology_additive_prediction_snapshots
  ADD COLUMN IF NOT EXISTS input_signature CHAR(64) NULL AFTER model_version;

ALTER TABLE enology_additive_prediction_snapshots
  ADD UNIQUE INDEX IF NOT EXISTS uq_enology_prediction_input (estate_id,wine_lot_id,model_version,input_signature);
