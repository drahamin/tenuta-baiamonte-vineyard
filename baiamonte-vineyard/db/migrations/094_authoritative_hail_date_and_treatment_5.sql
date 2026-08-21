-- Owner-authoritative correction received 2026-08-21:
-- the estate-wide hailstorm occurred during the evening of 2026-06-26.
-- No exact clock time was supplied. The first field report remains dated
-- 2026-06-27, while event_date and the stable chain key record occurrence.

UPDATE vineyard_damage_assessments
SET event_key='hail-2026-06-26',
    event_date='2026-06-26',
    notes=CONCAT_WS('\n',NULLIF(notes,''),
      'Authoritative owner correction 2026-08-21: the hailstorm occurred during the evening of 2026-06-26; exact clock time was not supplied. Assessment timestamps remain the dates of their reports.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND event_key='hail-2026-06-27';

UPDATE scouting_observations
SET damage_event_key='hail-2026-06-26'
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND damage_event_key='hail-2026-06-27';

-- Treatment 5 was applied on 2026-06-27, after the prior-evening hailstorm.
-- The owner confirms the products and per-100-L rates, but not the water
-- volume. Preserve the unknown totals instead of inventing stock consumption.
INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT a.estate_id,'owner-correction','confirm_completed','treatment',a.id,
       JSON_OBJECT('purpose',a.purpose,'status',a.status,'application_date',a.application_date,'water_volume_l',a.water_volume_l),
       JSON_OBJECT('purpose','Treatment 5','status','completed','application_date','2026-06-27','water_volume_l',400,
         'reason','Owner-authoritative confirmation on 2026-08-21; standard vineyard water volume and product rates confirmed')
FROM spray_applications a
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.crop_scope='vineyard' AND LOWER(TRIM(a.purpose))='treatment 5';

DELETE m FROM inventory_movements m
JOIN spray_application_items i ON m.reference_type='spray_application_item' AND m.reference_id=i.id
JOIN spray_applications a ON a.id=i.application_id
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.crop_scope='vineyard' AND LOWER(TRIM(a.purpose))='treatment 5';

DELETE i FROM spray_application_items i
JOIN spray_applications a ON a.id=i.application_id
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.crop_scope='vineyard' AND LOWER(TRIM(a.purpose))='treatment 5';

UPDATE spray_applications
SET application_date='2026-06-27 12:00:00',
    planned_application_date='2026-06-26',
    status='completed',
    water_volume_l=400,
    source_water_text='400 L · standard vineyard volume confirmed by owner 2026-08-21',
    evidence_status='owner-confirmed application, water volume, products and per-100-L rates; safety details pending',
    actual_details_confirmed=0,
    source_products='RESOLVE\nMICROTHIOL DISPERSS\nOSSICLOR 35 WG\nFRONTIERE\nREPENTE\nGEL DI SILICE',
    source_doses='RESOLVE: 500 g/100 L\nMICROTHIOL DISPERSS: 450 g/100 L\nOSSICLOR 35 WG: 340 g/100 L\nFRONTIERE: 150 ml/100 L\nREPENTE: 300 ml/100 L\nGEL DI SILICE: 450 ml/100 L',
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),
      '[OWNER AUTHORITATIVE 2026-08-21] Treatment 5 was applied on 2026-06-27 after the hailstorm on the evening of 2026-06-26. The standard vineyard volume was 400 L. Products, per-100-L rates and calculated total use are confirmed. Exact application time, treated scope, operator, weather, PHI/REI checks, PPE and exact mixture approval remain unconfirmed.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND crop_scope='vineyard' AND LOWER(TRIM(purpose))='treatment 5';

INSERT INTO spray_application_items
  (id,application_id,product_id,dose_amount,dose_unit,total_used,phi_days,notes)
SELECT UUID(),a.id,p.id,x.dose_amount,x.dose_unit,x.total_used,NULL,
  'Owner-authoritative applied product and per-100-L rate. Total used is the documented rate multiplied by the owner-confirmed 400 L standard vineyard volume.'
FROM spray_applications a
JOIN (
  SELECT 'RESOLVE' product_name,500 dose_amount,'g/100 L' dose_unit,2000 total_used UNION ALL
  SELECT 'MICROTHIOL DISPERSS',450,'g/100 L',1800 UNION ALL
  SELECT 'OSSICLOR 35 WG',340,'g/100 L',1360 UNION ALL
  SELECT 'FRONTIERE',150,'ml/100 L',600 UNION ALL
  SELECT 'REPENTE',300,'ml/100 L',1200 UNION ALL
  SELECT 'GEL DI SILICE',450,'ml/100 L',1800
) x
JOIN products p ON p.estate_id=a.estate_id AND p.name=x.product_name
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.crop_scope='vineyard' AND LOWER(TRIM(a.purpose))='treatment 5';

-- Post the confirmed total use to the authoritative inventory ledger. The
-- ledger intentionally permits negative balances while delayed invoices net in.
INSERT INTO inventory_movements
  (id,estate_id,product_id,movement_date,movement_type,quantity_delta,reference_type,reference_id,notes)
SELECT UUID(),a.estate_id,i.product_id,a.application_date,'use',
  CASE
    WHEN p.unit='kg' AND i.dose_unit LIKE 'g/%' THEN -ROUND(i.total_used/1000,3)
    WHEN p.unit='g' AND i.dose_unit LIKE 'g/%' THEN -ROUND(i.total_used,3)
    WHEN p.unit='L' AND LOWER(i.dose_unit) LIKE 'ml/%' THEN -ROUND(i.total_used/1000,3)
    WHEN p.unit='ml' AND LOWER(i.dose_unit) LIKE 'ml/%' THEN -ROUND(i.total_used,3)
  END,
  'spray_application_item',i.id,
  CONCAT('Owner-confirmed Treatment 5 use · 400 L standard vineyard volume · ',p.name,
    ' · source total ',i.total_used,' ',SUBSTRING_INDEX(i.dose_unit,'/',1),'.')
FROM spray_application_items i
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.crop_scope='vineyard' AND LOWER(TRIM(a.purpose))='treatment 5'
  AND ((p.unit='kg' AND i.dose_unit LIKE 'g/%') OR (p.unit='g' AND i.dose_unit LIKE 'g/%')
    OR (p.unit='L' AND LOWER(i.dose_unit) LIKE 'ml/%') OR (p.unit='ml' AND LOWER(i.dose_unit) LIKE 'ml/%'));

UPDATE tasks t
JOIN spray_applications a ON a.estate_id=t.estate_id
  AND LOWER(TRIM(t.title))=LOWER(TRIM(CONCAT('Treatment plan · ',a.purpose)))
SET t.status='done',t.completed_at=COALESCE(t.completed_at,'2026-06-27 12:00:00')
WHERE a.crop_scope='vineyard' AND LOWER(TRIM(a.purpose))='treatment 5';
