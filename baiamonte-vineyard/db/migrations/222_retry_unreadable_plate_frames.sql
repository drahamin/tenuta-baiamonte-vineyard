-- Earlier plate learning rows were written even when no plate crop was
-- available. Remove only those empty attempt markers so retained frames can
-- receive the new lower-vehicle search-crop pass. Evidence and movements stay
-- unchanged, and a new attempt marker prevents repeated OCR expenditure.
DELETE FROM estate_vehicle_plate_reads
WHERE plate_pattern IS NULL AND confidence_pct < 45;
