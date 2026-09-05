ALTER TABLE weather_observations
  ADD COLUMN feels_like_c DECIMAL(7,3) NULL AFTER temp_c,
  ADD COLUMN dew_point_c DECIMAL(7,3) NULL AFTER humidity_pct,
  ADD COLUMN vpd_kpa DECIMAL(7,3) NULL AFTER dew_point_c,
  ADD COLUMN rain_rate_mm_h DECIMAL(10,3) NULL AFTER rain_mm,
  ADD COLUMN wind_direction_10m_deg DECIMAL(7,2) NULL AFTER wind_direction_deg,
  ADD COLUMN gust_max_today_kph DECIMAL(8,3) NULL AFTER wind_gust_kph,
  ADD COLUMN sensor_battery_v DECIMAL(7,3) NULL AFTER soil_temp_c,
  ADD COLUMN sensor_capacitor_v DECIMAL(7,3) NULL AFTER sensor_battery_v;

ALTER TABLE weather_daily
  ADD COLUMN dew_point_avg_c DECIMAL(7,3) NULL AFTER humidity_avg_pct,
  ADD COLUMN vpd_avg_kpa DECIMAL(7,3) NULL AFTER dew_point_avg_c,
  ADD COLUMN rain_rate_max_mm_h DECIMAL(10,3) NULL AFTER rain_mm,
  ADD COLUMN leaf_wetness_avg_pct DECIMAL(7,3) NULL AFTER vpd_avg_kpa,
  ADD COLUMN soil_temp_avg_c DECIMAL(7,3) NULL AFTER soil_moisture_avg_pct;
