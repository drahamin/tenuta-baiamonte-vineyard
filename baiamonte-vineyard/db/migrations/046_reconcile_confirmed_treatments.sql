UPDATE spray_applications
SET planned_application_date=COALESCE(planned_application_date,DATE(application_date)),
    status='completed'
WHERE status='planned'
  AND LOWER(COALESCE(notes,'')) LIKE '%completion confirmed by user%'
  AND LOWER(COALESCE(notes,'')) LIKE '%source status: applied%';
