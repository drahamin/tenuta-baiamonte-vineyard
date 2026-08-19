-- These imported July rows explicitly retain the source statement that David
-- Rahamin confirmed each daily entry on 2026-08-15. Restore that named approver
-- without inventing an approval timestamp.
UPDATE labor_entries
SET approved_by='David Rahamin'
WHERE approved_by IS NULL
  AND approval_status='approved'
  AND source_labor_id LIKE 'APPLE-MSG-MATTIA-2026-%'
  AND notes LIKE '%Daily entry confirmed by David Rahamin on 2026-08-15.%';
