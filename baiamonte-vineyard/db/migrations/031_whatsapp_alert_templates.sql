ALTER TABLE alert_preferences
  ADD COLUMN IF NOT EXISTS whatsapp_template_name VARCHAR(180) NULL AFTER whatsapp_recipients,
  ADD COLUMN IF NOT EXISTS whatsapp_template_language VARCHAR(20) NULL AFTER whatsapp_template_name;
