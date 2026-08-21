-- Treatment audit reliability: exact-mixture reviews are bound to the current
-- structured recipe, and proven mass-to-mass inventory postings are repaired.

CREATE TABLE IF NOT EXISTS treatment_mixture_approvals (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  application_id CHAR(36) NOT NULL,
  mixture_signature CHAR(64) NOT NULL,
  product_count SMALLINT UNSIGNED NOT NULL,
  status ENUM('verified','rejected') NOT NULL,
  jar_test_status ENUM('passed','not_required','failed','not_recorded') NOT NULL DEFAULT 'not_recorded',
  current_labels_confirmed TINYINT(1) NOT NULL DEFAULT 0,
  exact_combination_confirmed TINYINT(1) NOT NULL DEFAULT 0,
  compatibility_basis TEXT NULL,
  sequence_notes TEXT NULL,
  approved_by VARCHAR(190) NULL,
  approved_at DATETIME(6) NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_treatment_mixture_application (estate_id,application_id),
  KEY ix_treatment_mixture_status (estate_id,status,active),
  CONSTRAINT fk_treatment_mixture_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_mixture_application FOREIGN KEY (application_id) REFERENCES spray_applications(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- FERTICUS 18 M is a verified wettable powder managed in kg. The source sheets
-- record g/100 L, so total_used grams must post as kilograms, not raw grams.
UPDATE inventory_movements m
JOIN spray_application_items i
  ON m.reference_type='spray_application_item' AND m.reference_id=i.id
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
SET m.quantity_delta=-ROUND(i.total_used/1000,3),
    m.notes=CONCAT('Confirmed treatment use: ',p.name,' · application ',a.id,
      ' · source total ',i.total_used,' g; converted to kg. [AUDIT REPAIR 2026-08-21]')
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.status IN ('completed','applied')
  AND p.name='FERTICUS 18 M'
  AND i.total_used IS NOT NULL
  AND LOWER(i.dose_unit) LIKE 'g/%';
