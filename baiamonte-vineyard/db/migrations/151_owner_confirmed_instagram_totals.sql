INSERT INTO social_account_snapshots
  (estate_id,platform,external_account_id,account_name,account_username,followers_count,following_count,media_count,captured_at,raw_metrics)
SELECT id,'instagram','17841475097812302','Tenuta Baiamonte','tenuta_baiamonte',313,1055,88,NOW(),
       JSON_OBJECT('source','owner_confirmed_instagram_profile_screenshot','confirmed_on','2026-09-06','followers_count',313,'follows_count',1055,'media_count',88)
FROM estates
WHERE id='00000000-0000-4000-8000-000000000001';

INSERT INTO social_audience_events
  (estate_id,platform,external_account_id,event_type,audience_change,previous_count,current_count,detected_at,snapshot_id)
SELECT estate_id,'instagram',external_account_id,'net_follow',4,309,313,NOW(),id
FROM social_account_snapshots
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND platform='instagram'
  AND JSON_UNQUOTE(JSON_EXTRACT(raw_metrics,'$.source'))='owner_confirmed_instagram_profile_screenshot'
ORDER BY id DESC LIMIT 1;
