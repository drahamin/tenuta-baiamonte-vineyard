-- Migration 098 briefly seeded invoice 429 as a fallback before the live FIC
-- refresh. Remove only that fallback and its generated mirror movement. The
-- real Fatture in Cloud evidence and receipt remain authoritative.
DELETE m FROM inventory_movements m
WHERE m.reference_type='fattureincloud_stock'
  AND m.reference_id='20260228-0429-0000-8000-000000000001';

DELETE FROM treatment_purchase_evidence
WHERE id='20260228-0429-0000-8000-000000000001'
  AND source_filename='owner-confirmed-invoice-429-2026';
