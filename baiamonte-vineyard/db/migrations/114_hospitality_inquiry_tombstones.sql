ALTER TABLE hospitality_inquiries
  MODIFY COLUMN status ENUM('new','responded','converted','closed','spam','deleted') NOT NULL DEFAULT 'new';
