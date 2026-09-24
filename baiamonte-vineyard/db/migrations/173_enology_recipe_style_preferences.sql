CREATE TABLE IF NOT EXISTS enology_recipe_preferences (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  plan_key VARCHAR(190) NOT NULL,
  wine_lot_id CHAR(36) NULL,
  variety_name VARCHAR(160) NULL,
  style_intensity TINYINT UNSIGNED NOT NULL DEFAULT 50,
  style_target VARCHAR(40) NOT NULL DEFAULT 'balanced',
  updated_by VARCHAR(160) NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_recipe_preference (estate_id,season_id,plan_key),
  KEY idx_enology_recipe_preference_lot (wine_lot_id),
  CONSTRAINT fk_enology_recipe_preference_estate FOREIGN KEY (estate_id) REFERENCES estates(id),
  CONSTRAINT fk_enology_recipe_preference_season FOREIGN KEY (season_id) REFERENCES seasons(id),
  CONSTRAINT fk_enology_recipe_preference_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE CASCADE
);
