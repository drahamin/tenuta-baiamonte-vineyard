DELETE imported
FROM lab_samples imported
JOIN lab_samples original
  ON original.estate_id=imported.estate_id
 AND original.lab_date=imported.lab_date
 AND LOWER(TRIM(original.sample_name))=LOWER(TRIM(imported.sample_name))
 AND original.id NOT IN (
   '44000000-0000-4000-8000-000000000101',
   '44000000-0000-4000-8000-000000000102',
   '44000000-0000-4000-8000-000000000103'
 )
WHERE imported.id IN (
  '44000000-0000-4000-8000-000000000101',
  '44000000-0000-4000-8000-000000000102',
  '44000000-0000-4000-8000-000000000103'
);
