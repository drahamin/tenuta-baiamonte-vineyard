-- Owner-confirmed purchased Grenache intake on 5 October 2026.
-- "Ganache" is normalized to the established Grenache variety. The supplied
-- source wording is preserved verbatim because the supplier/plot spelling has
-- not yet been corroborated by a delivery or purchase document.

INSERT INTO cellar_containers
  (id,estate_id,code,name,container_type,material,capacity_l,location,status,notes,active)
SELECT '20200000-0000-4000-8000-000000000001',e.id,'T-GRN-PUR-1000',
       'Purchased Grenache 1,000 L tank','tank',NULL,1000.00,'Raiti host cellar','in_use',
       'Owner-confirmed 5 October 2026: completely full with 1,078 kg of purchased, destemmed Grenache fruit from "Steph Yim''s 1200 plot". The 1,000 L figure is nominal vessel capacity/full working occupancy including grapes and skins; it is not a measured liquid-must or finished-wine yield. Physical tank number and construction material were not supplied.',1
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM cellar_containers c WHERE c.estate_id=e.id AND c.code='T-GRN-PUR-1000'
);

INSERT INTO cellar_control_profiles
  (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,manual_volume_l,manual_stage,
   manual_temp_c,manual_reading_at,manual_updated_at,updated_by)
SELECT '20200000-0000-4000-8000-000000000002',c.estate_id,c.id,'manual','not_configured',
       'Purchased Grenache 2026 — destemmed grapes/must with skins',1000.000,'cold hold / pre-fermentation',
       6.000,'2026-10-05 00:00:00','2026-10-05 00:00:00','Owner update 2026-10-05'
FROM cellar_containers c
WHERE c.code='T-GRN-PUR-1000'
ON DUPLICATE KEY UPDATE reading_mode=VALUES(reading_mode),sensor_status=VALUES(sensor_status),
  manual_contents=VALUES(manual_contents),manual_volume_l=VALUES(manual_volume_l),
  manual_stage=VALUES(manual_stage),manual_temp_c=VALUES(manual_temp_c),
  manual_reading_at=VALUES(manual_reading_at),manual_updated_at=VALUES(manual_updated_at),updated_by=VALUES(updated_by);

INSERT INTO harvest_lots
  (id,estate_id,season_id,lot_code,block_id,variety_id,harvested_at,weight_kg,field_weight_kg,
   winery_weight_kg,winery_weighed_at,winery_weight_notes,destination,fruit_temp_c,status,notes)
SELECT '20200000-0000-4000-8000-000000000003',s.estate_id,s.id,'2026-GRN-PUR-01',NULL,v.id,
       '2026-10-05 00:00:00',1078.00,1078.00,1078.00,'2026-10-05 00:00:00',
       'Owner-confirmed purchased/received fruit weight: 1,078 kg. Gross, tare, crates, weighing method and exact time were not supplied.',
       'Raiti host cellar',6.000,'received',
       'Purchased fruit, not an estate-block harvest. Owner supplied source wording: "Steph Yim''s 1200 plot". Preserve this wording pending supplier/delivery documentation. Destemmed 5 October 2026; tannin and sulfur were added; fruit was placed in a completely full nominal 1,000 L tank at 6 C. Fermentation had not started. Some grapes/must must be removed for safe headspace before adjustments and fermentation begin on 6 October.'
FROM seasons s
JOIN grape_varieties v ON v.estate_id=s.estate_id AND LOWER(v.name)='grenache'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE block_id=VALUES(block_id),variety_id=VALUES(variety_id),harvested_at=VALUES(harvested_at),
  weight_kg=VALUES(weight_kg),field_weight_kg=VALUES(field_weight_kg),winery_weight_kg=VALUES(winery_weight_kg),
  winery_weighed_at=VALUES(winery_weighed_at),winery_weight_notes=VALUES(winery_weight_notes),
  destination=VALUES(destination),fruit_temp_c=VALUES(fruit_temp_c),status=VALUES(status),notes=VALUES(notes);

INSERT INTO wine_lots
  (id,estate_id,season_id,code,harvest_lot_reference,name,stage,lot_status,volume_l,fruit_kg,initial_l,
   variety_summary,current_container_id,started_at,notes)
SELECT '20200000-0000-4000-8000-000000000004',s.estate_id,s.id,'GRN-2026-02','2026-GRN-PUR-01',
       'Purchased Grenache 2026 — Steph Yim''s 1200 plot','must','cold_hold',NULL,1078.000,NULL,
       'Grenache',c.id,'2026-10-05 00:00:00',
       'Separate purchased-fruit lot. Owner-confirmed intake 1,078 kg on 5 October 2026. Destemmed into a nominal 1,000 L tank that is completely full; the tank occupancy includes grapes and skins and is not entered as a measured liquid volume or yield. Current temperature 6 C. Fermentation not started. Tannin and sulfur were applied during destemming, but product identities, quantities, product lots and exact application times were not supplied. Source wording is "Steph Yim''s 1200 plot" pending documentary confirmation.'
FROM seasons s
JOIN cellar_containers c ON c.estate_id=s.estate_id AND c.code='T-GRN-PUR-1000'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE harvest_lot_reference=VALUES(harvest_lot_reference),name=VALUES(name),stage=VALUES(stage),
  lot_status=VALUES(lot_status),volume_l=VALUES(volume_l),fruit_kg=VALUES(fruit_kg),initial_l=VALUES(initial_l),
  variety_summary=VALUES(variety_summary),current_container_id=VALUES(current_container_id),
  started_at=VALUES(started_at),notes=VALUES(notes);

INSERT INTO cellar_lot_trace_records
  (id,estate_id,season_id,harvest_lot_id,wine_lot_id,container_id,transferred_at,fruit_kg,must_l,notes,recorded_by)
SELECT '20200000-0000-4000-8000-000000000005',h.estate_id,h.season_id,h.id,w.id,c.id,
       '2026-10-05 00:00:00',1078.000,NULL,
       'Exact trace from purchased Grenache intake 2026-GRN-PUR-01 to separate lot GRN-2026-02 and nominal 1,000 L vessel T-GRN-PUR-1000. Vessel reported completely full, but liquid-must volume was not measured and therefore remains NULL.',
       'Owner update 2026-10-05'
FROM harvest_lots h
JOIN wine_lots w ON w.season_id=h.season_id AND w.code='GRN-2026-02'
JOIN cellar_containers c ON c.id=w.current_container_id
WHERE h.lot_code='2026-GRN-PUR-01'
ON DUPLICATE KEY UPDATE harvest_lot_id=VALUES(harvest_lot_id),wine_lot_id=VALUES(wine_lot_id),
  container_id=VALUES(container_id),fruit_kg=VALUES(fruit_kg),must_l=VALUES(must_l),notes=VALUES(notes),recorded_by=VALUES(recorded_by);

INSERT INTO cellar_operations
  (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,amount,unit,temp_c,notes)
SELECT '20200000-0000-4000-8000-000000000006',s.estate_id,s.id,w.id,w.current_container_id,
       '2026-10-05 00:00:00','Purchased fruit reception and destemming',1078.000,'kg',6.000,
       'Owner-confirmed received and destemmed on 5 October 2026. Exact operation time, gross/tare basis, crate count and weighing method were not supplied.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-02'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),
  amount=VALUES(amount),unit=VALUES(unit),temp_c=VALUES(temp_c),notes=VALUES(notes);

INSERT INTO cellar_operations
  (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,temp_c,notes)
SELECT '20200000-0000-4000-8000-000000000007',s.estate_id,s.id,w.id,w.current_container_id,
       '2026-10-05 00:00:00','Cold hold before fermentation',6.000,
       'Tank reported completely full at 6 C. Fermentation had not started. Remove and measure enough grapes/must to establish safe fermentation headspace before adjustments and inoculation/start. Exact removed quantity and final working volume remain pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-02'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),
  temp_c=VALUES(temp_c),notes=VALUES(notes);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,
   reason_text,approved_by,approved_at,recorded_by)
SELECT '20200000-0000-4000-8000-000000000008',s.estate_id,w.id,
       'Tannin — exact product pending','tannin','applied','2026-10-05 00:00:00',NULL,NULL,NULL,
       'Owner-confirmed tannin addition during destemming on 5 October 2026. Exact product, dose, unit, product lot and application time were not supplied; no dose is inferred.',
       'David Rahamin','2026-10-05 00:00:00','Owner update 2026-10-05'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-02'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),
  event_status=VALUES(event_status),applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),
  product_lot=VALUES(product_lot),reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),
  approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,
   reason_text,approved_by,approved_at,recorded_by)
SELECT '20200000-0000-4000-8000-000000000009',s.estate_id,w.id,
       'Sulfur — exact product pending','other','applied','2026-10-05 00:00:00',NULL,NULL,NULL,
       'Owner-confirmed sulfur addition during destemming on 5 October 2026. Exact sulfur product/concentration, dose, unit, product lot and application time were not supplied; no SO2 dose is inferred.',
       'David Rahamin','2026-10-05 00:00:00','Owner update 2026-10-05'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-02'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),
  event_status=VALUES(event_status),applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),
  product_lot=VALUES(product_lot),reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),
  approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,addition_action,
   sensory_observation,owner_text,next_check_at,status)
SELECT '20200000-0000-4000-8000-000000000010',s.estate_id,w.id,'owner-purchased-grenache-2026-10-05',
       '2026-10-05 00:00:00',c.code,'cold hold / pre-fermentation',6.000,
       'Tannin and sulfur added during destemming; exact products and doses pending.',
       'Owner reported the nominal 1,000 L vessel completely full. Fermentation not started. Headspace must be created before fermentation.',
       'David Rahamin','2026-10-06 00:00:00','owner_confirmed_date_only'
FROM seasons s
JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-02'
JOIN cellar_containers c ON c.id=w.current_container_id
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at),vessel_name=VALUES(vessel_name),stage=VALUES(stage),
  temp_c=VALUES(temp_c),addition_action=VALUES(addition_action),sensory_observation=VALUES(sensory_observation),
  owner_text=VALUES(owner_text),next_check_at=VALUES(next_check_at),status=VALUES(status);

INSERT INTO tasks
  (id,estate_id,season_id,title,category,status,priority,due_date,notes,source)
SELECT '20200000-0000-4000-8000-000000000011',s.estate_id,s.id,
       'Create headspace and begin purchased Grenache fermentation','enology','planned','urgent','2026-10-06',
       'For lot GRN-2026-02 in T-GRN-PUR-1000: before fermentation, remove and measure enough grapes/must to establish safe headspace. Record removed quantity, final vessel occupancy/working volume, temperature, Babo/density and any adjustment, yeast/inoculation, additive product, dose, lot and exact start time. Do not infer a liquid yield from the current full-vessel observation. Enologist/owner approval governs the actual adjustment and fermentation procedure.',
       'owner_update'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE title=VALUES(title),category=VALUES(category),status=VALUES(status),priority=VALUES(priority),
  due_date=VALUES(due_date),notes=VALUES(notes),source=VALUES(source);

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '20200000-0000-4000-8000-000000000012',s.estate_id,'2026-10-05 00:00:00',
       'Purchased Grenache intake and pre-fermentation cold hold',
       'Owner update, 5 October 2026: purchased 1,078 kg of Grenache (message said "ganache") from "Steph Yim''s 1200 plot". The supplied source wording is retained pending documentary confirmation. Fruit was destemmed into a nominal 1,000 L tank and the vessel is completely full. This is vessel occupancy with grapes and skins, not a measured 1,000 L liquid yield. Fruit/must temperature is 6 C and fermentation has not started. Tannin and sulfur were added during destemming; products, doses, units, lots and exact time were not supplied. On 6 October the team plans to remove and measure enough material for safe headspace, make the approved adjustments, and begin fermentation.',
       JSON_ARRAY('owner-confirmed','purchased-fruit','grenache','destemming','cold-hold','pre-fermentation','2026'),
       'wine_lot',w.id
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-02'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

INSERT INTO historical_note_facts
  (id,estate_id,source_note_id,source_note_name,fact_key,fact_date,fact_year,date_precision,domain,subject,
   quantity_value,quantity_unit,details,evidence_status,canonical_table,canonical_key,conflict_note)
SELECT '20200000-0000-4000-8000-000000000013',s.estate_id,'owner-purchased-grenache-2026-10-05',
       'Owner update - purchased Grenache intake','purchased-grenache-intake','2026-10-05',2026,'day','cellar',
       'Purchased Grenache from "Steph Yim''s 1200 plot"',1078.000,'kg',
       'Purchased fruit; destemmed with tannin and sulfur; nominal 1,000 L vessel completely full at 6 C; fermentation not started. Vessel capacity is not treated as measured liquid yield.',
       'owner_confirmed','harvest_lots','2026-GRN-PUR-01',
       'Supplier spelling/legal identity, plot identifier, purchase document, tank physical number/material, exact operation time, additive products/doses/lots and liquid must volume remain pending.'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE fact_date=VALUES(fact_date),quantity_value=VALUES(quantity_value),quantity_unit=VALUES(quantity_unit),
  details=VALUES(details),evidence_status=VALUES(evidence_status),canonical_table=VALUES(canonical_table),
  canonical_key=VALUES(canonical_key),conflict_note=VALUES(conflict_note);

INSERT INTO mass_balance_records
  (id,estate_id,harvest_lot_reference,block_reference,variety_name,net_grapes_kg,must_wine_l,
   reconciliation_status,owner_text,notes)
SELECT '20200000-0000-4000-8000-000000000014',s.estate_id,'2026-GRN-PUR-01',
       'Purchased source: Steph Yim''s 1200 plot','Grenache',1078.000,NULL,
       'intake_recorded_yield_pending','David Rahamin',
       '1,078 kg purchased fruit is exact per owner. The nominal 1,000 L tank is completely full with grapes/must/skins, but no liquid yield has been measured; must_wine_l remains NULL until pressing or measurement.'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE block_reference=VALUES(block_reference),variety_name=VALUES(variety_name),
  net_grapes_kg=VALUES(net_grapes_kg),must_wine_l=VALUES(must_wine_l),
  reconciliation_status=VALUES(reconciliation_status),owner_text=VALUES(owner_text),notes=VALUES(notes);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-202','record_purchased_grenache_cold_hold','wine_lot','GRN-2026-02',
       JSON_OBJECT('date','2026-10-05','normalized_variety','Grenache','source_wording','Steph Yim''s 1200 plot',
                   'purchased_fruit_kg',1078,'container_code','T-GRN-PUR-1000','nominal_capacity_l',1000,
                   'container_full',TRUE,'measured_liquid_l',NULL,'temperature_c',6,'fermentation_started',FALSE,
                   'destemmed',TRUE,'additions',JSON_ARRAY('tannin - details pending','sulfur - details pending'),
                   'next_action_date','2026-10-06','invented_values',FALSE)
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-202'
    AND a.action='record_purchased_grenache_cold_hold' AND a.entity_id='GRN-2026-02'
);
