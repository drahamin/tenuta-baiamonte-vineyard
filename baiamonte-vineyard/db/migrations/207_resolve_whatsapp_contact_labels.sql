-- Replace unresolved direct-chat titles with the sender profile name already
-- captured on the message. Group titles are deliberately left unchanged.

UPDATE intake_items i
JOIN integration_events e
  ON e.estate_id=i.estate_id
 AND e.integration_name='system-whatsapp-channel'
 AND e.direction='inbound'
 AND e.event_type='message_received'
 AND JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.record_id'))=i.id
SET i.title=CONCAT(
      SUBSTRING_INDEX(i.title,' · Unnamed WhatsApp contact',1),
      ' · ',i.sender_name
    )
WHERE i.source='whatsapp'
  AND i.title LIKE '% · Unnamed WhatsApp contact · …%'
  AND JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.is_group')) IN ('false','0')
  AND COALESCE(i.sender_name,'') NOT IN ('','WhatsApp','WhatsApp chat','WhatsApp contact')
  AND i.sender_name NOT LIKE 'Unnamed WhatsApp contact%'
  AND i.sender_name NOT REGEXP '^[0-9]{7,}$';
