-- Correct four historical imports whose sample type disagreed with the
-- owner-supplied CI.MA.LAB report index. Results and source labels are retained.
UPDATE lab_samples
SET sample_type='wine',
    review_notes=CONCAT_WS('\n', NULLIF(review_notes,''), 'Sample type corrected from authoritative CI.MA.LAB report index (migration 124).')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND lab_date='2025-10-08'
  AND sample_type='must'
  AND canonical_sample_name='grenache';

UPDATE lab_samples
SET sample_type='wine',
    review_notes=CONCAT_WS('\n', NULLIF(review_notes,''), 'Sample type corrected from authoritative CI.MA.LAB report index (migration 124).')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND lab_date='2025-10-11'
  AND sample_type='other'
  AND canonical_sample_name='nerello mascalese';

UPDATE lab_samples
SET sample_type='wine',
    review_notes=CONCAT_WS('\n', NULLIF(review_notes,''), 'Sample type corrected from authoritative CI.MA.LAB report index (migration 124).')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND lab_date='2025-10-27'
  AND sample_type='other'
  AND canonical_sample_name IN ('grecanico','nerello mascalese');
