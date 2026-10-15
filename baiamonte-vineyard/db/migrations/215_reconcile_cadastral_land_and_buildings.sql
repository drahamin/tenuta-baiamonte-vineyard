ALTER TABLE cadastral_parcels
  ADD COLUMN record_type ENUM('land','building') NOT NULL DEFAULT 'land' AFTER parcel_number;

UPDATE cadastral_parcels
SET record_type='building'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND cadastral_sheet='83'
  AND parcel_number IN ('94','95');

INSERT INTO cadastral_parcels
  (id,estate_id,municipality,cadastral_sheet,parcel_number,record_type,tenure,contract_protocol,tenure_start,tenure_end,cadastral_area_ha,conducted_area_ha,buildings_m2,official_vineyard_area_ha,notes)
SELECT UUID(),id,'Randazzo','83','78','land','Comodato','AGEA.CAA6470.2024.0000391','2024-02-01','2044-12-31',2.4453,2.4453,0,NULL,
       'Official land parcel from cadastral record T166480/2026; verified map boundary still required'
FROM estates
WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE
  record_type='land',
  cadastral_area_ha=VALUES(cadastral_area_ha),
  notes=VALUES(notes);
