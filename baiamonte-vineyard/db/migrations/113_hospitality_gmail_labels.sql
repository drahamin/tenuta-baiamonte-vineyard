ALTER TABLE intake_items
    ADD COLUMN IF NOT EXISTS source_metadata JSON NULL AFTER message_text;
