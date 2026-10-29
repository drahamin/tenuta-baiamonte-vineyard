-- Reconcile only unambiguous 2026 values from the signed Consoli 2026/2027
-- service contract. Contract estimates are not invoices; ambiguous or optional
-- charges remain NULL until the actual service and tax treatment are confirmed.
UPDATE olive_cost_models m
JOIN estates e ON e.id=m.estate_id AND e.slug='tenuta-baiamonte'
SET
  m.press_rate_eur_per_kg=COALESCE(m.press_rate_eur_per_kg,0.1800),
  m.package_3l_unit_cost_eur=COALESCE(m.package_3l_unit_cost_eur,4.2700),
  m.source_as_of='2026-10-29',
  m.notes=CONCAT_WS('\n',NULLIF(m.notes,''),
    'Consoli 2026/2027 signed contract applied where unambiguous: milling €0.18/kg VAT included; 3 L can service €3.50 net plus 22% VAT = €4.27/unit for the planned 1–59 tier. Contract references only, pending supplier invoice.',
    'Contract reference estimates not treated as reconciled: standard filtering €120 with VAT and immediate-filter surcharge unresolved; 500 ml packaging €2.20 net/unit with glass inclusion and label printing unresolved; manual sheet-label application €0.20 net/bottle if used; storage €0.28/kg with €50 minimum below 200 kg if used.',
    'Pending named evidence: Nunzio performed transport and will invoice it. Giancarlo will report harvest crew hours; Giancarlo time is additional.'),
  m.updated_by='Consoli contract reconciliation 2026-10-29'
WHERE m.record_year=2026;
