CREATE TABLE IF NOT EXISTS finance_parties (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  party_type ENUM('customer','supplier','both','owner','employee','government','bank','other') NOT NULL DEFAULT 'other',
  name VARCHAR(220) NOT NULL,
  internal_code VARCHAR(80) NULL,
  vat_id VARCHAR(80) NULL,
  tax_code VARCHAR(80) NULL,
  email VARCHAR(190) NULL,
  certified_email VARCHAR(190) NULL,
  phone VARCHAR(80) NULL,
  contact_name VARCHAR(160) NULL,
  address_line VARCHAR(255) NULL,
  city VARCHAR(120) NULL,
  postal_code VARCHAR(30) NULL,
  province VARCHAR(80) NULL,
  country VARCHAR(100) NULL,
  iban VARCHAR(80) NULL,
  sdi_code VARCHAR(30) NULL,
  payment_terms VARCHAR(120) NULL,
  default_payment_method VARCHAR(120) NULL,
  notes TEXT NULL,
  source VARCHAR(80) NOT NULL DEFAULT 'manual',
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_finance_party_name (estate_id, name),
  KEY ix_finance_party_vat (estate_id, vat_id),
  CONSTRAINT fk_finance_party_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_accounts (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  account_code VARCHAR(80) NOT NULL,
  parent_id CHAR(36) NULL,
  account_name VARCHAR(220) NOT NULL,
  account_type ENUM('asset','liability','equity','revenue','expense','tax','memorandum') NOT NULL,
  reporting_category VARCHAR(120) NULL,
  deductible_pct DECIMAL(7,4) NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  notes TEXT NULL,
  UNIQUE KEY uq_finance_account_code (estate_id, account_code),
  CONSTRAINT fk_finance_account_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_finance_account_parent FOREIGN KEY (parent_id) REFERENCES finance_accounts(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cost_centers (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  code VARCHAR(80) NOT NULL,
  name VARCHAR(180) NOT NULL,
  center_type ENUM('vineyard','cellar','olive','sales','administration','capital_project','private_excluded','other') NOT NULL,
  block_id CHAR(36) NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  notes TEXT NULL,
  UNIQUE KEY uq_cost_center_code (estate_id, code),
  CONSTRAINT fk_cost_center_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_cost_center_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS financial_documents (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  document_type ENUM('sales_invoice','purchase_invoice','credit_note','debit_note','receipt','payroll','tax_notice','other') NOT NULL,
  document_number VARCHAR(100) NOT NULL,
  document_date DATE NOT NULL,
  due_date DATE NULL,
  party_id CHAR(36) NULL,
  currency CHAR(3) NOT NULL DEFAULT 'EUR',
  taxable_amount DECIMAL(16,2) NOT NULL DEFAULT 0,
  vat_amount DECIMAL(16,2) NOT NULL DEFAULT 0,
  withholding_tax DECIMAL(16,2) NOT NULL DEFAULT 0,
  social_security_withholding DECIMAL(16,2) NOT NULL DEFAULT 0,
  gross_total DECIMAL(16,2) NOT NULL DEFAULT 0,
  deductible_pct DECIMAL(7,4) NULL,
  vat_deductible_pct DECIMAL(7,4) NULL,
  depreciation_years SMALLINT UNSIGNED NULL,
  status ENUM('draft','issued','received','part_paid','paid','void','disputed') NOT NULL DEFAULT 'received',
  payment_status ENUM('unpaid','part_paid','paid','not_applicable','unknown') NOT NULL DEFAULT 'unknown',
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  source_document VARCHAR(500) NULL,
  external_source_id VARCHAR(190) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_financial_document (estate_id, document_type, document_number, document_date),
  KEY ix_fin_document_date_type (estate_id, document_date, document_type),
  KEY ix_fin_document_party (party_id, document_date),
  CONSTRAINT fk_fin_document_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_fin_document_party FOREIGN KEY (party_id) REFERENCES finance_parties(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS financial_document_lines (
  id CHAR(36) PRIMARY KEY,
  document_id CHAR(36) NOT NULL,
  line_number SMALLINT UNSIGNED NOT NULL,
  description VARCHAR(700) NOT NULL,
  product_id CHAR(36) NULL,
  account_id CHAR(36) NULL,
  cost_center_id CHAR(36) NULL,
  season_id CHAR(36) NULL,
  work_activity_id CHAR(36) NULL,
  quantity DECIMAL(16,4) NULL,
  unit VARCHAR(40) NULL,
  unit_price DECIMAL(16,4) NULL,
  taxable_amount DECIMAL(16,2) NOT NULL DEFAULT 0,
  vat_rate DECIMAL(7,4) NULL,
  vat_amount DECIMAL(16,2) NOT NULL DEFAULT 0,
  deductible_pct DECIMAL(7,4) NULL,
  vat_deductible_pct DECIMAL(7,4) NULL,
  company_share_pct DECIMAL(7,4) NOT NULL DEFAULT 1,
  private_excluded TINYINT(1) NOT NULL DEFAULT 0,
  notes TEXT NULL,
  UNIQUE KEY uq_fin_document_line (document_id, line_number),
  CONSTRAINT fk_fin_line_document FOREIGN KEY (document_id) REFERENCES financial_documents(id) ON DELETE CASCADE,
  CONSTRAINT fk_fin_line_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
  CONSTRAINT fk_fin_line_account FOREIGN KEY (account_id) REFERENCES finance_accounts(id) ON DELETE SET NULL,
  CONSTRAINT fk_fin_line_center FOREIGN KEY (cost_center_id) REFERENCES cost_centers(id) ON DELETE SET NULL,
  CONSTRAINT fk_fin_line_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_fin_line_activity FOREIGN KEY (work_activity_id) REFERENCES work_activities(id) ON DELETE SET NULL,
  CONSTRAINT ck_fin_line_company_share CHECK (company_share_pct >= 0 AND company_share_pct <= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cash_accounts (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(160) NOT NULL,
  account_type ENUM('bank','credit_card','cash','owner_clearing','other') NOT NULL,
  institution VARCHAR(160) NULL,
  iban_masked VARCHAR(80) NULL,
  currency CHAR(3) NOT NULL DEFAULT 'EUR',
  opening_balance DECIMAL(16,2) NOT NULL DEFAULT 0,
  opening_date DATE NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_cash_account_name (estate_id, name),
  CONSTRAINT fk_cash_account_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cash_transactions (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  cash_account_id CHAR(36) NOT NULL,
  transaction_date DATE NOT NULL,
  value_date DATE NULL,
  description TEXT NOT NULL,
  party_id CHAR(36) NULL,
  transaction_type ENUM('customer_receipt','supplier_payment','owner_contribution','owner_draw','bank_fee','tax','transfer','refund','other') NOT NULL DEFAULT 'other',
  amount_in DECIMAL(16,2) NOT NULL DEFAULT 0,
  amount_out DECIMAL(16,2) NOT NULL DEFAULT 0,
  running_balance DECIMAL(16,2) NULL,
  external_source_id VARCHAR(190) NULL,
  reconciliation_status ENUM('unmatched','part_matched','matched','excluded','review') NOT NULL DEFAULT 'unmatched',
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_cash_external (estate_id, cash_account_id, external_source_id),
  KEY ix_cash_transaction_date (cash_account_id, transaction_date),
  CONSTRAINT fk_cash_transaction_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_cash_transaction_account FOREIGN KEY (cash_account_id) REFERENCES cash_accounts(id) ON DELETE CASCADE,
  CONSTRAINT fk_cash_transaction_party FOREIGN KEY (party_id) REFERENCES finance_parties(id) ON DELETE SET NULL,
  CONSTRAINT ck_cash_one_direction CHECK (NOT (amount_in > 0 AND amount_out > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cash_allocations (
  id CHAR(36) PRIMARY KEY,
  cash_transaction_id CHAR(36) NOT NULL,
  document_id CHAR(36) NULL,
  account_id CHAR(36) NULL,
  cost_center_id CHAR(36) NULL,
  allocated_amount DECIMAL(16,2) NOT NULL,
  notes TEXT NULL,
  CONSTRAINT fk_cash_alloc_transaction FOREIGN KEY (cash_transaction_id) REFERENCES cash_transactions(id) ON DELETE CASCADE,
  CONSTRAINT fk_cash_alloc_document FOREIGN KEY (document_id) REFERENCES financial_documents(id) ON DELETE SET NULL,
  CONSTRAINT fk_cash_alloc_account FOREIGN KEY (account_id) REFERENCES finance_accounts(id) ON DELETE SET NULL,
  CONSTRAINT fk_cash_alloc_center FOREIGN KEY (cost_center_id) REFERENCES cost_centers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inventory_snapshots (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  product_id CHAR(36) NOT NULL,
  snapshot_date DATE NOT NULL,
  quantity_on_hand DECIMAL(16,3) NULL,
  opening_quantity DECIMAL(16,3) NULL,
  average_cost DECIMAL(16,4) NULL,
  average_sales_price DECIMAL(16,4) NULL,
  inventory_value DECIMAL(16,2) NULL,
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  notes TEXT NULL,
  UNIQUE KEY uq_inventory_snapshot (estate_id, product_id, snapshot_date),
  CONSTRAINT fk_inventory_snapshot_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_inventory_snapshot_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS price_entries (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  product_id CHAR(36) NULL,
  vintage_year SMALLINT UNSIGNED NULL,
  wine_name VARCHAR(160) NOT NULL,
  channel ENUM('restaurant_bar','vineyard','wholesale','export','other') NOT NULL,
  effective_date DATE NOT NULL,
  price_net DECIMAL(16,4) NULL,
  price_gross DECIMAL(16,4) NULL,
  vat_rate DECIMAL(7,4) NULL,
  currency CHAR(3) NOT NULL DEFAULT 'EUR',
  status ENUM('historical','current','planned') NOT NULL DEFAULT 'current',
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  notes TEXT NULL,
  UNIQUE KEY uq_price_entry (estate_id, wine_name, vintage_year, channel, effective_date),
  CONSTRAINT fk_price_entry_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_price_entry_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS financial_scenarios (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(100) NOT NULL,
  scenario_type ENUM('actual','base','upside','downside','custom') NOT NULL,
  selected TINYINT(1) NOT NULL DEFAULT 0,
  start_year SMALLINT UNSIGNED NULL,
  end_year SMALLINT UNSIGNED NULL,
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  notes TEXT NULL,
  UNIQUE KEY uq_financial_scenario (estate_id, name),
  CONSTRAINT fk_financial_scenario_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS forecast_assumptions (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  scenario_id CHAR(36) NULL,
  assumption_key VARCHAR(160) NOT NULL,
  assumption_group VARCHAR(120) NULL,
  effective_year SMALLINT UNSIGNED NULL,
  numeric_value DECIMAL(20,8) NULL,
  text_value TEXT NULL,
  unit VARCHAR(40) NULL,
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  notes TEXT NULL,
  UNIQUE KEY uq_forecast_assumption (estate_id, scenario_id, assumption_key, effective_year),
  CONSTRAINT fk_forecast_assumption_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_forecast_assumption_scenario FOREIGN KEY (scenario_id) REFERENCES financial_scenarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS annual_financial_summary (
  estate_id CHAR(36) NOT NULL,
  fiscal_year SMALLINT UNSIGNED NOT NULL,
  scenario_id CHAR(36) NOT NULL,
  revenue DECIMAL(18,2) NULL,
  goods_inputs DECIMAL(18,2) NULL,
  production_services DECIMAL(18,2) NULL,
  vehicle_costs DECIMAL(18,2) NULL,
  professional_technical DECIMAL(18,2) NULL,
  travel_admin_representation DECIMAL(18,2) NULL,
  software_licenses DECIMAL(18,2) NULL,
  payroll DECIMAL(18,2) NULL,
  depreciation DECIMAL(18,2) NULL,
  other_operating_costs DECIMAL(18,2) NULL,
  total_operating_costs DECIMAL(18,2) NULL,
  operating_result DECIMAL(18,2) NULL,
  income_tax DECIMAL(18,2) NULL,
  after_tax_result DECIMAL(18,2) NULL,
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (estate_id, fiscal_year, scenario_id),
  CONSTRAINT fk_annual_fin_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_annual_fin_scenario FOREIGN KEY (scenario_id) REFERENCES financial_scenarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS monthly_financial_summary (
  estate_id CHAR(36) NOT NULL,
  fiscal_year SMALLINT UNSIGNED NOT NULL,
  fiscal_month TINYINT UNSIGNED NOT NULL,
  actual_revenue DECIMAL(18,2) NULL,
  actual_cost DECIMAL(18,2) NULL,
  budget_revenue DECIMAL(18,2) NULL,
  budget_cost DECIMAL(18,2) NULL,
  latest_forecast_revenue DECIMAL(18,2) NULL,
  latest_forecast_cost DECIMAL(18,2) NULL,
  status ENUM('closed','pending','planned') NOT NULL DEFAULT 'planned',
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  notes TEXT NULL,
  PRIMARY KEY (estate_id, fiscal_year, fiscal_month),
  CONSTRAINT fk_monthly_fin_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT ck_monthly_fin_month CHECK (fiscal_month BETWEEN 1 AND 12)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vat_returns (
  estate_id CHAR(36) NOT NULL,
  fiscal_year SMALLINT UNSIGNED NOT NULL,
  filing_status ENUM('draft','filed','amended','forecast') NOT NULL,
  sales_net DECIMAL(18,2) NULL,
  taxable_purchases DECIMAL(18,2) NULL,
  output_vat DECIMAL(18,2) NULL,
  input_vat DECIMAL(18,2) NULL,
  annual_credit DECIMAL(18,2) NULL,
  prior_credit DECIMAL(18,2) NULL,
  credit_used DECIMAL(18,2) NULL,
  refund_requested DECIMAL(18,2) NULL,
  refund_received DECIMAL(18,2) NULL,
  vat_payable DECIMAL(18,2) NULL,
  ending_credit DECIMAL(18,2) NULL,
  income_tax DECIMAL(18,2) NULL,
  source_document VARCHAR(500) NULL,
  assumptions_confirmed_by VARCHAR(160) NULL,
  notes TEXT NULL,
  PRIMARY KEY (estate_id, fiscal_year, filing_status),
  CONSTRAINT fk_vat_return_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS account_balance_lines (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  fiscal_year SMALLINT UNSIGNED NOT NULL,
  section VARCHAR(80) NOT NULL,
  account_code VARCHAR(80) NOT NULL,
  description VARCHAR(255) NOT NULL,
  book_amount DECIMAL(18,2) NULL,
  non_deductible_pct DECIMAL(7,4) NULL,
  non_deductible_amount DECIMAL(18,2) NULL,
  tax_amount DECIMAL(18,2) NULL,
  source_document VARCHAR(500) NULL,
  UNIQUE KEY uq_account_balance_line (estate_id, fiscal_year, account_code),
  CONSTRAINT fk_account_balance_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_service_costs (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  fiscal_year SMALLINT UNSIGNED NOT NULL,
  service_type VARCHAR(160) NOT NULL,
  party_id CHAR(36) NULL,
  person_name VARCHAR(180) NOT NULL,
  amount_eur DECIMAL(18,2) NULL,
  record_status ENUM('actual','budget','unknown','review') NOT NULL DEFAULT 'unknown',
  basis_note TEXT NULL,
  source VARCHAR(100) NOT NULL DEFAULT 'manual',
  UNIQUE KEY uq_contract_service (estate_id, fiscal_year, service_type, person_name),
  CONSTRAINT fk_contract_service_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_contract_service_party FOREIGN KEY (party_id) REFERENCES finance_parties(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS capital_projects (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  code VARCHAR(80) NOT NULL,
  name VARCHAR(220) NOT NULL,
  site VARCHAR(160) NULL,
  owner_payer VARCHAR(220) NULL,
  company_project TINYINT(1) NOT NULL DEFAULT 1,
  private_excluded TINYINT(1) NOT NULL DEFAULT 0,
  status ENUM('idea','diligence','planning','application','approved','contracting','in_progress','complete','cancelled','on_hold') NOT NULL DEFAULT 'planning',
  planned_start DATE NULL,
  planned_end DATE NULL,
  budget_low DECIMAL(18,2) NULL,
  budget_high DECIMAL(18,2) NULL,
  actual_cost DECIMAL(18,2) NULL,
  decision_gate TEXT NULL,
  notes TEXT NULL,
  UNIQUE KEY uq_capital_project_code (estate_id, code),
  CONSTRAINT fk_capital_project_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS capital_budget_lines (
  id CHAR(36) PRIMARY KEY,
  project_id CHAR(36) NOT NULL,
  cost_code VARCHAR(80) NOT NULL,
  description VARCHAR(500) NOT NULL,
  cost_category VARCHAR(120) NULL,
  owner_payer VARCHAR(220) NULL,
  target_timing VARCHAR(80) NULL,
  budget_low DECIMAL(18,2) NULL,
  budget_high DECIMAL(18,2) NULL,
  support_low_pct DECIMAL(7,4) NULL,
  support_high_pct DECIMAL(7,4) NULL,
  primary_route_text VARCHAR(255) NULL,
  eligibility_gate TEXT NULL,
  commitment_status ENUM('uncommitted','approved_to_quote','approved_to_order','committed','paid','cancelled') NOT NULL DEFAULT 'uncommitted',
  private_excluded TINYINT(1) NOT NULL DEFAULT 0,
  UNIQUE KEY uq_capital_budget_line (project_id, cost_code),
  CONSTRAINT fk_capital_line_project FOREIGN KEY (project_id) REFERENCES capital_projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS funding_opportunities (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_opportunity_id VARCHAR(40) NOT NULL,
  program_name VARCHAR(300) NOT NULL,
  program_level VARCHAR(120) NULL,
  status VARCHAR(120) NOT NULL,
  fit VARCHAR(80) NULL,
  priority ENUM('low','medium','high','critical') NOT NULL DEFAULT 'medium',
  opens_on DATE NULL,
  deadline DATE NULL,
  support_type VARCHAR(160) NULL,
  rate_amount TEXT NULL,
  eligible_use TEXT NULL,
  eligibility_risk TEXT NULL,
  project_role TEXT NULL,
  next_action TEXT NULL,
  owner_text VARCHAR(180) NULL,
  last_verified DATE NULL,
  confidence_timing TEXT NULL,
  official_source_url VARCHAR(900) NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_funding_opportunity (estate_id, source_opportunity_id),
  CONSTRAINT fk_funding_opportunity_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS funding_applications (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  opportunity_id CHAR(36) NOT NULL,
  project_id CHAR(36) NULL,
  application_reference VARCHAR(160) NULL,
  status ENUM('screening','preparing','submitted','clarification','approved','rejected','withdrawn','closed') NOT NULL DEFAULT 'screening',
  requested_amount DECIMAL(18,2) NULL,
  approved_amount DECIMAL(18,2) NULL,
  support_rate DECIMAL(7,4) NULL,
  submitted_on DATE NULL,
  decision_on DATE NULL,
  permitted_commitment_date DATE NULL,
  retention_until DATE NULL,
  dedicated_cash_account_id CHAR(36) NULL,
  owner_text VARCHAR(180) NULL,
  notes TEXT NULL,
  CONSTRAINT fk_funding_application_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_funding_application_opportunity FOREIGN KEY (opportunity_id) REFERENCES funding_opportunities(id) ON DELETE RESTRICT,
  CONSTRAINT fk_funding_application_project FOREIGN KEY (project_id) REFERENCES capital_projects(id) ON DELETE SET NULL,
  CONSTRAINT fk_funding_application_cash FOREIGN KEY (dedicated_cash_account_id) REFERENCES cash_accounts(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS funding_requirements (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  opportunity_id CHAR(36) NULL,
  category VARCHAR(100) NOT NULL,
  requirement_name VARCHAR(300) NOT NULL,
  programs_text VARCHAR(255) NULL,
  owner_text VARCHAR(180) NULL,
  status ENUM('not_started','in_progress','complete','not_applicable','blocked','expired') NOT NULL DEFAULT 'not_started',
  due_date DATE NULL,
  evidence_reference_id CHAR(36) NULL,
  evidence_url VARCHAR(900) NULL,
  notes TEXT NULL,
  UNIQUE KEY uq_funding_requirement (estate_id, category, requirement_name),
  CONSTRAINT fk_funding_requirement_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_funding_requirement_opp FOREIGN KEY (opportunity_id) REFERENCES funding_opportunities(id) ON DELETE SET NULL,
  CONSTRAINT fk_funding_requirement_evidence FOREIGN KEY (evidence_reference_id) REFERENCES evidence_references(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS funding_milestones (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  project_id CHAR(36) NULL,
  phase VARCHAR(80) NULL,
  starts_on DATE NULL,
  ends_on DATE NULL,
  workstream VARCHAR(180) NOT NULL,
  action_text TEXT NOT NULL,
  owner_text VARCHAR(180) NULL,
  priority ENUM('low','medium','high','critical','conditional') NOT NULL DEFAULT 'medium',
  status ENUM('not_started','in_progress','complete','blocked','cancelled') NOT NULL DEFAULT 'not_started',
  dependency_guardrail TEXT NULL,
  funding_target VARCHAR(255) NULL,
  spend_permission TEXT NULL,
  decision_gate TEXT NULL,
  deliverable TEXT NULL,
  notes TEXT NULL,
  CONSTRAINT fk_funding_milestone_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_funding_milestone_project FOREIGN KEY (project_id) REFERENCES capital_projects(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS funding_allocations (
  id CHAR(36) PRIMARY KEY,
  application_id CHAR(36) NOT NULL,
  budget_line_id CHAR(36) NULL,
  document_line_id CHAR(36) NULL,
  allocation_role ENUM('primary','permitted_secondary','excluded','pending_review') NOT NULL DEFAULT 'primary',
  eligible_cost DECIMAL(18,2) NULL,
  support_amount DECIMAL(18,2) NULL,
  eligibility_status ENUM('unknown','eligible','partly_eligible','ineligible','pending_written_advice') NOT NULL DEFAULT 'unknown',
  written_approval_reference VARCHAR(500) NULL,
  notes TEXT NULL,
  UNIQUE KEY uq_primary_document_funding (document_line_id, allocation_role),
  CONSTRAINT fk_funding_allocation_application FOREIGN KEY (application_id) REFERENCES funding_applications(id) ON DELETE CASCADE,
  CONSTRAINT fk_funding_allocation_budget FOREIGN KEY (budget_line_id) REFERENCES capital_budget_lines(id) ON DELETE SET NULL,
  CONSTRAINT fk_funding_allocation_document FOREIGN KEY (document_line_id) REFERENCES financial_document_lines(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fixed_assets (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  asset_code VARCHAR(100) NOT NULL,
  name VARCHAR(220) NOT NULL,
  asset_category VARCHAR(120) NULL,
  equipment_id CHAR(36) NULL,
  project_id CHAR(36) NULL,
  acquisition_document_line_id CHAR(36) NULL,
  acquisition_date DATE NULL,
  placed_in_service_date DATE NULL,
  acquisition_cost DECIMAL(18,2) NULL,
  company_share_pct DECIMAL(7,4) NOT NULL DEFAULT 1,
  depreciation_years SMALLINT UNSIGNED NULL,
  accumulated_depreciation DECIMAL(18,2) NULL,
  serial_number VARCHAR(160) NULL,
  location VARCHAR(160) NULL,
  grant_sensitive TINYINT(1) NOT NULL DEFAULT 0,
  retention_until DATE NULL,
  status ENUM('planned','ordered','installed','in_service','disposed','retired') NOT NULL DEFAULT 'planned',
  notes TEXT NULL,
  UNIQUE KEY uq_fixed_asset_code (estate_id, asset_code),
  CONSTRAINT fk_fixed_asset_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_fixed_asset_equipment FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE SET NULL,
  CONSTRAINT fk_fixed_asset_project FOREIGN KEY (project_id) REFERENCES capital_projects(id) ON DELETE SET NULL,
  CONSTRAINT fk_fixed_asset_document_line FOREIGN KEY (acquisition_document_line_id) REFERENCES financial_document_lines(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE products ADD COLUMN IF NOT EXISTS sku VARCHAR(80) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS category_name VARCHAR(100) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS sales_price_net DECIMAL(16,4) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS sales_price_gross DECIMAL(16,4) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS vat_rate DECIMAL(7,4) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS purchase_price DECIMAL(16,4) NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS track_inventory TINYINT(1) NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS uq_products_estate_sku ON products (estate_id, sku);

INSERT IGNORE INTO cost_centers (id,estate_id,code,name,center_type) VALUES
  (UUID(),'00000000-0000-4000-8000-000000000001','VINEYARD','Vineyard operations','vineyard'),
  (UUID(),'00000000-0000-4000-8000-000000000001','CELLAR','Cellar and winemaking','cellar'),
  (UUID(),'00000000-0000-4000-8000-000000000001','OLIVE','Olive operations','olive'),
  (UUID(),'00000000-0000-4000-8000-000000000001','SALES','Sales and distribution','sales'),
  (UUID(),'00000000-0000-4000-8000-000000000001','ADMIN','Administration','administration'),
  (UUID(),'00000000-0000-4000-8000-000000000001','PRIVATE','Private / excluded','private_excluded');
