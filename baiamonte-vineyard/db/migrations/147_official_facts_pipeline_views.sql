CREATE OR REPLACE VIEW v_official_vineyard_basis AS
SELECT d.estate_id,d.id source_document_id,d.issue_date source_issue_date,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(d.verified_facts,'$.official_vineyard_area_m2')) AS DECIMAL(12,2)) official_registered_m2,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(d.verified_facts,'$.official_vineyard_area_m2')) AS DECIMAL(12,2))/10000 official_registered_ha,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(e.metadata,'$.pending_new_planting_area_ha')) AS DECIMAL(10,4)) pending_new_planting_ha,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(e.metadata,'$.working_total_planted_area_ha')) AS DECIMAL(10,4)) working_planted_area_ha,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(e.metadata,'$.current_production_area_ha')) AS DECIMAL(10,4)) current_productive_area_ha,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(e.metadata,'$.projected_productive_area_ha_2027')) AS DECIMAL(10,4)) projected_productive_area_ha,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(e.metadata,'$.expected_productive_year')) AS UNSIGNED) expected_productive_year,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(r.verified_facts,'$.reported_vineyard_area_m2')) AS DECIMAL(12,2)) incomplete_reference_extract_m2,
  'authoritative_complete_register' authority_basis,'pending_documentation' new_planting_status
FROM official_documents d
LEFT JOIN evidence_references e ON e.estate_id=d.estate_id AND e.id='evidence-new-vines-registration'
LEFT JOIN official_documents r ON r.estate_id=d.estate_id AND r.document_type='vineyard_register' AND r.status='reference'
WHERE d.document_type='vineyard_register' AND d.status='current'
  AND JSON_EXTRACT(d.verified_facts,'$.official_vineyard_area_m2') IS NOT NULL;

CREATE OR REPLACE VIEW v_official_harvest_declarations AS
SELECT estate_id,effective_year vintage_year,id source_document_id,issue_date source_issue_date,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(verified_facts,'$.total_grapes_kg')) AS DECIMAL(12,2)) total_grapes_kg,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(verified_facts,'$.white_grapes_kg')) AS DECIMAL(12,2)) white_grapes_kg,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(verified_facts,'$.red_grapes_kg')) AS DECIMAL(12,2)) red_grapes_kg,
  verified_facts,'official_declaration' authority_basis
FROM official_documents
WHERE document_type='harvest_declaration' AND status='current';
