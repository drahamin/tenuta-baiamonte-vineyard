ALTER TABLE harvest_lots
  ADD COLUMN IF NOT EXISTS field_weight_kg DECIMAL(12,3) NULL AFTER weight_kg,
  ADD COLUMN IF NOT EXISTS winery_weight_kg DECIMAL(12,3) NULL AFTER field_weight_kg,
  ADD COLUMN IF NOT EXISTS winery_weighed_at DATETIME(6) NULL AFTER winery_weight_kg,
  ADD COLUMN IF NOT EXISTS winery_weight_notes TEXT NULL AFTER winery_weighed_at;

UPDATE harvest_lots
SET field_weight_kg = weight_kg
WHERE field_weight_kg IS NULL;

CREATE TABLE IF NOT EXISTS harvest_lot_blocks (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  harvest_lot_id CHAR(36) NOT NULL,
  block_id CHAR(36) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_harvest_lot_block (harvest_lot_id, block_id),
  KEY idx_harvest_lot_blocks_estate (estate_id),
  KEY idx_harvest_lot_blocks_block (block_id),
  CONSTRAINT fk_harvest_lot_blocks_estate FOREIGN KEY (estate_id) REFERENCES estates(id),
  CONSTRAINT fk_harvest_lot_blocks_lot FOREIGN KEY (harvest_lot_id) REFERENCES harvest_lots(id) ON DELETE CASCADE,
  CONSTRAINT fk_harvest_lot_blocks_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id)
);

INSERT IGNORE INTO harvest_lot_blocks (id, estate_id, harvest_lot_id, block_id)
SELECT UUID(), estate_id, id, block_id
FROM harvest_lots
WHERE block_id IS NOT NULL;
