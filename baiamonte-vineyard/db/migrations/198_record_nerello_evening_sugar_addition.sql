-- Owner update supplied 30 September 2026: 10.5 kg of the established
-- Naturalia crystalMUSTGRAPE alcohol-consistency product was added to the
-- Nerello during the evening pump-over. The Wendy chronology identifies the
-- pump-over as evening but does not give an exact clock time, so 19:00 remains
-- an explicitly approximate storage time shared with that operation.

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '19800000-0000-4000-8000-000000000001',s.estate_id,w.id,'crystalMUSTGRAPE','other','applied',
       '2026-09-30 19:00:00',10.5000,'kg',NULL,
       'Owner-confirmed 10.5 kg sugar addition to the Nerello during the 30 September evening pump-over. Recorded as the established Naturalia crystalMUSTGRAPE alcohol-consistency product used by the estate. 19:00 is an approximate storage time; exact clock time and product lot were not supplied. Retest potential alcohol after complete homogenization before considering any further addition. This sugar addition changes fermentable load but does not by itself authorize another nutrient dose.',
       'David Rahamin','2026-09-30 19:00:00','Owner update 2026-09-30'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

UPDATE cellar_operations o
JOIN wine_lots w ON w.id=o.wine_lot_id AND w.code='NM-2026-01'
SET o.notes=CONCAT_WS(' ',NULLIF(o.notes,''),'Owner update: 10.5 kg Naturalia crystalMUSTGRAPE added during this pump-over for alcohol consistency; exact clock time and product lot were not supplied.')
WHERE o.id='19700000-0000-4000-8000-000000000056'
  AND COALESCE(o.notes,'') NOT LIKE '%10.5 kg Naturalia crystalMUSTGRAPE%';

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id AND p.normalized_name='crystalmustgrape'
SET st.quantity_status='unverified',
    st.notes=CONCAT_WS(' ',NULLIF(st.notes,''),'Owner confirmed 10.5 kg used in NM-2026-01 on 30 September 2026. Remaining cellar stock is not inferred because the received quantity was not supplied.')
WHERE COALESCE(st.notes,'') NOT LIKE '%10.5 kg used in NM-2026-01%';

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '19800000-0000-4000-8000-000000000002',s.estate_id,'2026-09-30 19:00:00',
       'Nerello evening pump-over and sugar addition',
       'Owner update: 10.5 kg of the established Naturalia crystalMUSTGRAPE alcohol-consistency product was added to the approximately 1,600 L Nerello lot during the evening pump-over. The exact clock time and product lot were not supplied; 19:00 is retained as an approximate storage time. Retest potential alcohol after homogenization before any further correction. Nutrient need remains a separate APA/YAN and fermentation-trajectory decision.',
       JSON_ARRAY('owner-confirmed','nerello-mascalese','pump-over','crystalmustgrape','alcohol-consistency','2026'),
       'wine_lot',w.id
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-198','record_nerello_sugar_addition','wine_lot','NM-2026-01',
       JSON_OBJECT('product','Naturalia crystalMUSTGRAPE','quantity',10.5,'unit','kg',
                   'applied_at','2026-09-30 19:00:00','time_precision','approximate evening',
                   'operation','pump-over','post_addition_test','potential alcohol after homogenization',
                   'nutrient_effect','No automatic nutrient authorization')
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-198' AND a.action='record_nerello_sugar_addition');
