UPDATE cadastral_parcels
SET cadastral_sheet=SUBSTRING_INDEX(cadastral_sheet,'.',1)
WHERE cadastral_sheet REGEXP '^[0-9]+\\.0$';

UPDATE cadastral_parcels
SET parcel_number=SUBSTRING_INDEX(parcel_number,'.',1)
WHERE parcel_number REGEXP '^[0-9]+\\.0$';

UPDATE cadastral_parcels SET official_vineyard_area_ha=0.1685
WHERE estate_id='00000000-0000-4000-8000-000000000001' AND cadastral_sheet='83' AND parcel_number='76';
UPDATE cadastral_parcels SET official_vineyard_area_ha=0.0093
WHERE estate_id='00000000-0000-4000-8000-000000000001' AND cadastral_sheet='83' AND parcel_number='77';
UPDATE cadastral_parcels SET official_vineyard_area_ha=0.7366
WHERE estate_id='00000000-0000-4000-8000-000000000001' AND cadastral_sheet='83' AND parcel_number='93';
