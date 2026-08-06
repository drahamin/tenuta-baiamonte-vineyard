ALTER TABLE labor_entries ADD COLUMN IF NOT EXISTS work_category VARCHAR(100) NULL;
ALTER TABLE labor_entries ADD COLUMN IF NOT EXISTS work_performed VARCHAR(500) NULL;
ALTER TABLE labor_entries ADD COLUMN IF NOT EXISTS location_text VARCHAR(180) NULL;
ALTER TABLE labor_entries ADD COLUMN IF NOT EXISTS start_time TIME NULL;
ALTER TABLE labor_entries ADD COLUMN IF NOT EXISTS end_time TIME NULL;
ALTER TABLE labor_entries ADD COLUMN IF NOT EXISTS other_cost_eur DECIMAL(12,2) NULL;
ALTER TABLE labor_entries ADD COLUMN IF NOT EXISTS entry_source VARCHAR(80) NOT NULL DEFAULT 'manual';

CREATE OR REPLACE VIEW v_contractor_hours AS
SELECT l.id,l.estate_id,l.work_date,l.person_or_crew,l.role,l.work_category,l.work_performed,l.location_text,
       l.start_time,l.end_time,l.regular_hours,l.overtime_hours,l.hourly_rate_eur,l.labor_cost_eur,l.other_cost_eur,
       COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0) total_cost,l.payment_status,l.notes,l.entry_source
FROM labor_entries l
WHERE l.payroll_scope IN ('contractor','payroll_excluded');
