ALTER TABLE intake_items
  MODIFY COLUMN source ENUM('upload','gmail','whatsapp','imessage','codex','chatgpt','home_assistant') NOT NULL;
