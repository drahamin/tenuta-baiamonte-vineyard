-- Earlier profiles used Rosso/Bianco/Rosato in wine_type before wine_color
-- became a separate field. The supplied host-cellar cards identify both live
-- 2026 products as Vino tranquillo; retain color independently.
UPDATE wine_lot_legal_profiles lp
JOIN wine_lots w ON w.id=lp.wine_lot_id AND w.estate_id=lp.estate_id
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
JOIN cellar_containers c ON c.id=w.current_container_id AND c.estate_id=w.estate_id
SET lp.wine_type='Vino tranquillo'
WHERE c.code IN ('T-03','M-01')
  AND (lp.wine_type IS NULL OR TRIM(lp.wine_type)='' OR lp.wine_type IN ('Rosso','Bianco','Rosato'));
