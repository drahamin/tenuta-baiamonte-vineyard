INSERT INTO inventory_movements (
  id,estate_id,product_id,movement_date,movement_type,quantity_delta,unit_cost_eur,
  reference_type,reference_id,notes
)
SELECT x.movement_id,e.id,p.id,x.movement_date,'purchase',x.quantity,x.unit_cost,
  'invoice_stock',x.purchase_evidence_id,x.notes
FROM estates e
JOIN (
  SELECT '20260530-1478-1000-8000-000000000002' movement_id,'SACRON 45 WG' product_name,'2026-05-30 12:00:00' movement_date,1 quantity,18.1800 unit_cost,'20260530-1478-0000-8000-000000000002' purchase_evidence_id,'Received into stock from Agriplanet invoice 1478; 1 x 1 kg.' notes UNION ALL
  SELECT '20260530-1478-1000-8000-000000000007','OSSICLOR 35 WG','2026-05-30 12:00:00',10,6.9550,'20260530-1478-0000-8000-000000000007','Received into stock from Agriplanet invoice 1478; 1 x 10 kg.' UNION ALL
  SELECT '20260630-1919-1000-8000-000000000001','IMPULSIVE PREMIUM','2026-06-30 12:00:00',5,16.5380,'20260630-1919-0000-8000-000000000001','Received into stock from Agriplanet invoice 1919; 5 x 1 L.' UNION ALL
  SELECT '20260630-1919-1000-8000-000000000002','RESOLVE','2026-06-30 12:00:00',10,15.9620,'20260630-1919-0000-8000-000000000002','Received into stock from Agriplanet invoice 1919; two 5 L packages combined.' UNION ALL
  SELECT '20260630-1919-1000-8000-000000000003','TERRAPLUS SOLUB NPK 8-7-6','2026-06-30 12:00:00',15,3.7180,'20260630-1919-0000-8000-000000000003','Received into stock from Agriplanet invoice 1919; 1 x 15 kg.' UNION ALL
  SELECT '20260630-1919-1000-8000-000000000005','GEL DI SILICE','2026-06-30 12:00:00',5,9.8360,'20260630-1919-0000-8000-000000000005','Received into stock from Agriplanet invoice 1919; 1 x 5 kg.'
) x
JOIN products p ON p.estate_id=e.id AND p.name=x.product_name
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE quantity_delta=VALUES(quantity_delta),unit_cost_eur=VALUES(unit_cost_eur),
  reference_type=VALUES(reference_type),reference_id=VALUES(reference_id),notes=VALUES(notes);
