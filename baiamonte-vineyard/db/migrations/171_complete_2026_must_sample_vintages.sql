-- Persist vintage context established by the approved RP 0771/26 report and
-- the 2026 cellar chronology. This supplies routing metadata only; it does
-- not approve, alter, or reinterpret any laboratory result.
UPDATE lab_samples
SET vintage_year=2026,
    vintage_assignment_source='source_report',
    vintage_assignment_confidence='confirmed',
    vintage_assignment_evidence='Approved RP 0771/26 report and 2026 cellar chronology'
WHERE id IN (
  '9c8982a6-cbc0-40e8-9fb2-f3f1a59114a0',
  '041c1d98-4e00-4bc2-a16d-f1b41b7c2a8d',
  'd44d173a-03bf-4a32-9022-057976f3c432',
  '0ba86bc0-4de7-4a54-ba1b-f100771a09ab',
  '9dc64de1-7505-406b-a836-0268745e2553'
) AND vintage_year IS NULL;
