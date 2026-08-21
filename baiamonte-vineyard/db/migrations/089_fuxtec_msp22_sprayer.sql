-- Owner-confirmed second estate sprayer. Manufacturer specifications establish
-- identity and nominal tank capacity only; actual usable fill and field
-- calibration remain deliberately unverified.

INSERT INTO equipment (id,estate_id,name,equipment_type,make_model,status,notes,active)
SELECT UUID(),e.id,'FUXTEC FX-MSP2.2 backpack motor sprayer','sprayer','FUXTEC FX-MSP2.2','available',
  'Owner-confirmed estate equipment. Manufacturer lists a 26 L chemical tank, 41.5 cm3 two-stroke motor and nominal liquid throughput above 4 L/min. Actual usable fill, installed nozzle, operating flow, pressure, walking speed and carrier L/ha require field calibration.',1
FROM estates e WHERE e.slug='tenuta-baiamonte'
  AND NOT EXISTS (SELECT 1 FROM equipment q WHERE q.estate_id=e.id AND q.make_model='FUXTEC FX-MSP2.2' AND q.equipment_type='sprayer');

INSERT INTO spray_equipment_profiles (id,estate_id,equipment_id,application_method,tank_capacity_l,calibration_status,source_reference,notes,active)
SELECT UUID(),q.estate_id,q.id,'water_spray',26,'needs_measurement',
  'https://fuxtec.fr/products/pulvrisateur-thermique-dos-atomiseur-fuxtec-fxmsp22',
  'Manufacturer nominal specification: 26 L chemical tank. Do not substitute the stated maximum machine throughput for measured nozzle flow or carrier rate; calibrate the physical estate unit before exact batch approval.',1
FROM equipment q WHERE q.make_model='FUXTEC FX-MSP2.2' AND q.equipment_type='sprayer'
ON DUPLICATE KEY UPDATE application_method='water_spray',tank_capacity_l=26,calibration_status=IF(calibration_status='verified','verified','needs_measurement'),source_reference=VALUES(source_reference),notes=VALUES(notes),active=1;
