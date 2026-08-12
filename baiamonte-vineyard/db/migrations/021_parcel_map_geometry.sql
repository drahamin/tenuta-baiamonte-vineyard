ALTER TABLE cadastral_parcels
  ADD COLUMN center_latitude DECIMAL(10,7) NULL AFTER official_vineyard_area_ha,
  ADD COLUMN center_longitude DECIMAL(10,7) NULL AFTER center_latitude,
  ADD COLUMN geometry_geojson JSON NULL AFTER center_longitude,
  ADD COLUMN map_url VARCHAR(700) NULL AFTER geometry_geojson;
