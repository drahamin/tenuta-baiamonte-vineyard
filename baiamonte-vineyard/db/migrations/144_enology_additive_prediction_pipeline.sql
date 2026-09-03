CREATE TABLE IF NOT EXISTS enology_product_protocols (
  id CHAR(36) PRIMARY KEY,
  product_catalog_id CHAR(36) NOT NULL,
  protocol_code VARCHAR(100) NOT NULL,
  protocol_name VARCHAR(220) NOT NULL,
  purpose VARCHAR(255) NOT NULL,
  wine_colors VARCHAR(80) NOT NULL DEFAULT 'any',
  process_stages VARCHAR(255) NOT NULL,
  trigger_code VARCHAR(80) NOT NULL,
  dose_min DECIMAL(12,4) NULL,
  dose_max DECIMAL(12,4) NULL,
  dose_unit VARCHAR(40) NULL,
  dose_basis VARCHAR(255) NULL,
  preparation TEXT NULL,
  application_instructions TEXT NULL,
  prerequisites TEXT NULL,
  incompatibilities TEXT NULL,
  minimum_contact_hours DECIMAL(12,2) NULL,
  source_url VARCHAR(700) NOT NULL,
  source_revision VARCHAR(80) NULL,
  verified_on DATE NOT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_product_protocol (product_catalog_id,protocol_code),
  KEY ix_enology_protocol_stage (process_stages,trigger_code,active),
  CONSTRAINT fk_enology_protocol_product FOREIGN KEY (product_catalog_id) REFERENCES enology_product_catalog(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE enology_process_profiles ADD COLUMN IF NOT EXISTS potential_alcohol_pct DECIMAL(6,3) NULL AFTER yan_target_mg_l;
ALTER TABLE enology_process_profiles ADD COLUMN IF NOT EXISTS must_turbidity_ntu DECIMAL(12,3) NULL AFTER potential_alcohol_pct;
ALTER TABLE enology_process_profiles ADD COLUMN IF NOT EXISTS fruit_condition VARCHAR(40) NOT NULL DEFAULT 'unknown' AFTER must_turbidity_ntu;
ALTER TABLE enology_process_profiles ADD COLUMN IF NOT EXISTS laccase_u_ml DECIMAL(12,4) NULL AFTER fruit_condition;
ALTER TABLE enology_process_profiles ADD COLUMN IF NOT EXISTS anthocyanin_tannin_ratio DECIMAL(12,4) NULL AFTER laccase_u_ml;
ALTER TABLE enology_process_profiles ADD COLUMN IF NOT EXISTS inoculated_at DATETIME(6) NULL AFTER anthocyanin_tannin_ratio;
ALTER TABLE enology_process_profiles ADD COLUMN IF NOT EXISTS planned_filtration_at DATETIME(6) NULL AFTER inoculated_at;

CREATE TABLE IF NOT EXISTS enology_additive_prediction_snapshots (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  model_version VARCHAR(80) NOT NULL,
  prediction_status VARCHAR(40) NOT NULL,
  due_count INT NOT NULL DEFAULT 0,
  blocked_count INT NOT NULL DEFAULT 0,
  pipeline_json JSON NOT NULL,
  predicted_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_enology_prediction_lot (estate_id,wine_lot_id,predicted_at),
  CONSTRAINT fk_enology_prediction_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_prediction_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO enology_product_protocols
  (id,product_catalog_id,protocol_code,protocol_name,purpose,wine_colors,process_stages,trigger_code,dose_min,dose_max,dose_unit,dose_basis,preparation,application_instructions,prerequisites,incompatibilities,minimum_contact_hours,source_url,source_revision,verified_on)
SELECT UUID(),p.id,x.protocol_code,x.protocol_name,x.purpose,x.wine_colors,x.process_stages,x.trigger_code,x.dose_min,x.dose_max,x.dose_unit,x.dose_basis,x.preparation,x.application_instructions,x.prerequisites,x.incompatibilities,x.minimum_contact_hours,x.source_url,x.source_revision,'2026-09-03'
FROM enology_product_catalog p
JOIN (
  SELECT 'zymaflore alpha' product_key,'dry_sequential' protocol_code,'Dry-wine sequential inoculation' protocol_name,'Complexity through sequential non-Saccharomyces and S. cerevisiae inoculation' purpose,'any' wine_colors,'must,pre-fermentation' process_stages,'inoculation' trigger_code,30 dose_min,30 dose_max,'g/hL' dose_unit,'Product data sheet: dry wines' dose_basis,'Rehydrate in water at 25–30°C, then follow the current packet rehydration protocol.' preparation,'Add ALPHA to must, then add an enologist-selected S. cerevisiae at 20 g/hL after 24–72 hours.' application_instructions,'Lot volume, wine style confirmed as dry, selected follow-on S. cerevisiae, enologist approval' prerequisites,'Avoid a must/yeast temperature difference above 10°C. Total yeast preparation time must not exceed 45 minutes.' incompatibilities,NULL minimum_contact_hours,'https://laffort.com/wp-content/uploads/FP/FP_EN_Zymaflore_Alpha.pdf' source_url,'current PDS accessed 2026-09-03' source_revision
  UNION ALL SELECT 'zymaflore f83','standard_inoculation','Standard red-wine inoculation','Fruity, supple Mediterranean red fermentation','red','must,pre-fermentation','inoculation',20,30,'g/hL','Product data sheet','Follow the current packet yeast-rehydration protocol.','Inoculate as soon as possible after rehydration.','Lot volume, potential alcohol, must temperature, YAN/APA, enologist approval','Avoid a must/yeast temperature difference above 10°C. Preparation must not exceed 45 minutes.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Zymaflore_F83.pdf','11.07.24'
  UNION ALL SELECT 'zymaflore rx60','standard_inoculation','Standard red-wine inoculation','Fruity and spicy red fermentation','red','must,pre-fermentation','inoculation',20,30,'g/hL','Product data sheet','Follow the current packet yeast-rehydration protocol.','Inoculate as soon as possible after rehydration.','Lot volume, potential alcohol, must temperature, YAN/APA, enologist approval','Avoid a must/yeast temperature difference above 10°C. Preparation must not exceed 45 minutes.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Zymaflore_RX60.pdf','11.07.24'
  UNION ALL SELECT 'zymaflore x16','standard_inoculation','Standard white/rosé inoculation','Aromatic white or rosé fermentation','white,rose','must,pre-fermentation','inoculation',20,30,'g/hL','Product data sheet','Follow the current packet yeast-rehydration protocol and acclimatise carefully for low-temperature inoculation.','Inoculate as soon as possible after rehydration.','Lot volume, potential alcohol, must temperature, YAN/APA, turbidity, enologist approval','Avoid a must/yeast temperature difference above 10°C. Preparation must not exceed 45 minutes.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Zymaflore_X16.pdf','10.12.19'
  UNION ALL SELECT 'lafazym press','pressing','White/rosé pressing enzyme','Juice yield and aroma-precursor extraction','white,rose','receiving,pressing,must','pressing',2,5,'g/100kg','Product data sheet','Follow the current product data sheet and homogenise throughout the fruit or must.','Add as early as possible before pressing. Adjust within the range for skin quality, maturity, and sanitation.','Recorded grape weight, skin condition, maturity, sanitation, enologist approval','Do not infer a dose from finished-wine volume.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Lafazym_Press.pdf','current PDS accessed 2026-09-03'
  UNION ALL SELECT 'lafase he grand cru','red_extraction','Structured-red extraction enzyme','Selective colour and polymerised-tannin extraction','red','receiving,must,fermentation','crusher_or_fermentation',3,5,'g/100kg','Product data sheet','Dissolve in 10 times its weight of water or must.','Add at the crusher, including during cold maceration. Infected grapes use 5 g/100 kg after fermentation starts.','Recorded grape weight, skin thickness, phenolic maturity, sanitation, enologist approval','Bentonite irreversibly inactivates the enzyme. Use bentonite only after enzyme activity or removal. Do not directly contact sulphurous solution.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Lafase_HE_Grand_Cru.pdf','04.06.24'
  UNION ALL SELECT 'nutristart thiols','first_third','First-third fermentation nutrition','Support fermentation and varietal-thiol expression','white,rose','fermentation','density_drop_30',20,60,'g/hL','Product data sheet, adjusted to must composition','Dissolve in 10 times its weight of must.','Add during the first third of fermentation after about a 30-point density drop. If nitrogen deficient, the sheet also permits use within 24 hours after inoculation.','Lot volume, measured YAN/APA, potential alcohol, turbidity, yeast strain, density baseline and current density, enologist approval','Do not calculate nutrient need from YAN deficit alone. Current sheet and applicable legal limits govern.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Nutristart_Thiols.pdf','13.03.2026'
  UNION ALL SELECT 'tanin vr color','clarification','Clarification tannin','Protein reaction and clarification support','red','must,fermentation','pump_over',10,30,'g/hL','Product data sheet: clarification use','No preliminary dissolution is required by the IDP process.','Add the full amount during a homogenising pump-over. After cold soaking, use the first pump-over after maceration.','Lot volume, selected purpose, phenolic/sanitary review, enologist approval','Purpose-specific ranges are not interchangeable.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Tanin_VR_Color.pdf','09.06.2023'
  UNION ALL SELECT 'tanin vr color','laccase','Laccase inhibition tannin','Review for measured laccase activity or Botrytis-affected fruit','red','receiving,must,fermentation','sanitary_evidence',30,80,'g/hL','Product data sheet: laccase inhibition','No preliminary dissolution is required by the IDP process.','Add during a homogenising pump-over at the enologist-selected timing.','Lot volume, Botrytis or laccase evidence, selected purpose, enologist approval','Blocked without sanitary or laccase evidence. Purpose-specific ranges are not interchangeable.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Tanin_VR_Color.pdf','09.06.2023'
  UNION ALL SELECT 'tanin vr supra','structural','Structural tannin','Structural improvement without added bitterness','red','must,fermentation','first_pump_over',10,20,'g/hL','Product data sheet: structural improvement','No preliminary dissolution is required. Homogenise into the must or wine.','On sound fruit, add the full amount during the first pump-over at the start of alcoholic fermentation.','Lot volume, phenolic review, selected purpose, enologist approval','Purpose-specific ranges are not interchangeable.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Tanin_VR_Supra.pdf','09.06.23'
  UNION ALL SELECT 'tanin vr supra','colour','Colour-stabilisation tannin','Colour stabilisation where the anthocyanin/tannin balance warrants review','red','must,fermentation','first_pump_over',20,40,'g/hL','Product data sheet: colour stabilisation','No preliminary dissolution is required. Homogenise into the must or wine.','Add the full amount during the first pump-over at the start of alcoholic fermentation.','Lot volume, anthocyanin/tannin or phenolic evidence, selected purpose, enologist approval','Purpose-specific ranges are not interchangeable.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Tanin_VR_Supra.pdf','09.06.23'
  UNION ALL SELECT 'tanin vr supra','laccase','Laccase-inhibition tannin','Review for measured laccase activity or Botrytis-affected fruit','red','receiving,must,fermentation','sanitary_evidence',30,80,'g/hL','Product data sheet: laccase inhibition','No preliminary dissolution is required. Homogenise into the must or wine.','For Botrytis-affected fruit, add early, ideally in the hopper.','Lot volume, Botrytis or laccase evidence, selected purpose, enologist approval','Blocked without sanitary or laccase evidence. Purpose-specific ranges are not interchangeable.',NULL,'https://laffort.com/wp-content/uploads/FP/FP_EN_Tanin_VR_Supra.pdf','09.06.23'
  UNION ALL SELECT 'oenofeel','ageing','Ageing mouthfeel treatment','Roundness, volume, aromatic expression, and balance during ageing','any','aging','ageing_review',10,30,'g/hL','Product data sheet','Dissolve in 5 to 10 times its volume of water.','Homogenise by pump-over in tanks or bâtonnage in barrels. Allow at least one week before filtration.','Lot volume, sensory bench trial, filtration plan, enologist approval','Minimum one-week contact before filtration. Do not use opened packaging.',168,'https://laffort.com/wp-content/uploads/FP/FP_EN_Oenofeel.pdf','17.12.25'
) x ON p.manufacturer='LAFFORT' AND p.normalized_name=x.product_key
ON DUPLICATE KEY UPDATE protocol_name=VALUES(protocol_name),purpose=VALUES(purpose),wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),trigger_code=VALUES(trigger_code),dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),preparation=VALUES(preparation),application_instructions=VALUES(application_instructions),prerequisites=VALUES(prerequisites),incompatibilities=VALUES(incompatibilities),minimum_contact_hours=VALUES(minimum_contact_hours),source_url=VALUES(source_url),source_revision=VALUES(source_revision),verified_on=VALUES(verified_on),active=1;

UPDATE enology_product_catalog p
JOIN (
  SELECT 'zymaflore f83' product_key,20 dose_min,30 dose_max,'g/hL' dose_unit,'Official product data sheet' dose_basis
  UNION ALL SELECT 'zymaflore rx60',20,30,'g/hL','Official product data sheet'
  UNION ALL SELECT 'zymaflore x16',20,30,'g/hL','Official product data sheet'
  UNION ALL SELECT 'lafase he grand cru',3,5,'g/100kg','Official product data sheet'
  UNION ALL SELECT 'nutristart thiols',20,60,'g/hL','Official product data sheet, adjusted to YAN/APA, potential alcohol, turbidity and yeast strain'
  UNION ALL SELECT 'oenofeel',10,30,'g/hL','Official product data sheet, desired sensory effect and bench trial'
) x ON p.manufacturer='LAFFORT' AND p.normalized_name=x.product_key
SET p.dose_min=x.dose_min,p.dose_max=x.dose_max,p.dose_unit=x.dose_unit,p.dose_basis=x.dose_basis,p.dose_verified=1;
