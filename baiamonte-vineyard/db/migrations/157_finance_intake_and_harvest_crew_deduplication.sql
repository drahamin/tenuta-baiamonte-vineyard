-- Keep one canonical evidence row for each owner-confirmed 2026 harvest crew.
-- These aliases duplicate the same date, shift, headcount and handled weight.

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT duplicate_entry.estate_id,'migration-157','merge_duplicate','labor',duplicate_entry.id,
       JSON_OBJECT('person_or_crew',duplicate_entry.person_or_crew,'work_date',duplicate_entry.work_date,'shift_label',duplicate_entry.shift_label,'kg_handled',duplicate_entry.kg_handled,'notes',duplicate_entry.notes),
       JSON_OBJECT('canonical_id',canonical.id,'canonical_source_labor_id',canonical.source_labor_id,'reason','Same harvest crew, date, shift, headcount and handled weight')
FROM labor_entries duplicate_entry
JOIN labor_entries canonical ON canonical.estate_id=duplicate_entry.estate_id
 AND canonical.source_labor_id=CASE duplicate_entry.id
   WHEN '05026d12-616c-47ff-ab01-0e4c2a8197eb' THEN 'wendy-2026-grecanico-harvest-crew'
   WHEN 'cae0a20e-4460-4b78-9786-b96b406cb8ca' THEN 'wendy-2026-grenache-harvest-crew'
 END
WHERE duplicate_entry.id IN ('05026d12-616c-47ff-ab01-0e4c2a8197eb','cae0a20e-4460-4b78-9786-b96b406cb8ca')
  AND NOT EXISTS (SELECT 1 FROM audit_events audit WHERE audit.estate_id=duplicate_entry.estate_id AND audit.actor='migration-157' AND audit.action='merge_duplicate' AND audit.entity_id=duplicate_entry.id);

UPDATE entity_attachments attachment
JOIN labor_entries duplicate_entry ON duplicate_entry.id=attachment.entity_id AND attachment.entity_type='labor'
JOIN labor_entries canonical ON canonical.estate_id=duplicate_entry.estate_id
 AND canonical.source_labor_id=CASE duplicate_entry.id
   WHEN '05026d12-616c-47ff-ab01-0e4c2a8197eb' THEN 'wendy-2026-grecanico-harvest-crew'
   WHEN 'cae0a20e-4460-4b78-9786-b96b406cb8ca' THEN 'wendy-2026-grenache-harvest-crew'
 END
SET attachment.entity_id=canonical.id
WHERE duplicate_entry.id IN ('05026d12-616c-47ff-ab01-0e4c2a8197eb','cae0a20e-4460-4b78-9786-b96b406cb8ca');

UPDATE labor_invoice_payments payment
JOIN labor_entries duplicate_entry ON duplicate_entry.id=payment.labor_entry_id
JOIN labor_entries canonical ON canonical.estate_id=duplicate_entry.estate_id
 AND canonical.source_labor_id=CASE duplicate_entry.id
   WHEN '05026d12-616c-47ff-ab01-0e4c2a8197eb' THEN 'wendy-2026-grecanico-harvest-crew'
   WHEN 'cae0a20e-4460-4b78-9786-b96b406cb8ca' THEN 'wendy-2026-grenache-harvest-crew'
 END
SET payment.labor_entry_id=canonical.id
WHERE duplicate_entry.id IN ('05026d12-616c-47ff-ab01-0e4c2a8197eb','cae0a20e-4460-4b78-9786-b96b406cb8ca');

DELETE duplicate_entry FROM labor_entries duplicate_entry
JOIN labor_entries canonical ON canonical.estate_id=duplicate_entry.estate_id
 AND canonical.source_labor_id=CASE duplicate_entry.id
   WHEN '05026d12-616c-47ff-ab01-0e4c2a8197eb' THEN 'wendy-2026-grecanico-harvest-crew'
   WHEN 'cae0a20e-4460-4b78-9786-b96b406cb8ca' THEN 'wendy-2026-grenache-harvest-crew'
 END
WHERE duplicate_entry.id IN ('05026d12-616c-47ff-ab01-0e4c2a8197eb','cae0a20e-4460-4b78-9786-b96b406cb8ca');
