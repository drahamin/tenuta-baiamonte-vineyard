-- Owner-confirmed legal variety names from the host cellar's current paper
-- labels. Keep the estate's operational/common name Grenache on the wine lot,
-- while recording Alicante under its legal Terre Siciliane IGT designation.
-- "Superiore" is part of the Grecanico designation, not a spelling variant.
UPDATE wine_lot_legal_profiles lp
JOIN wine_lots w ON w.id=lp.wine_lot_id AND w.estate_id=lp.estate_id
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
JOIN cellar_containers c ON c.id=w.current_container_id AND c.estate_id=w.estate_id
SET lp.denomination_class=CASE
      WHEN c.code='M-01' THEN 'IGP Terre Siciliane'
      WHEN c.code='T-03' THEN 'Sicilia DOC'
      ELSE lp.denomination_class
    END,
    lp.denomination=CASE
      WHEN c.code='M-01' THEN 'Alicante'
      WHEN c.code='T-03' THEN 'Grecanico Superiore'
      ELSE lp.denomination
    END,
    lp.legal_notes=CONCAT_WS(
      '\n', NULLIF(lp.legal_notes,''),
      CASE
        WHEN c.code='M-01' THEN 'Owner-corrected 2026-09-16: operational variety Grenache; legal designation Terre Siciliane IGT Alicante. It is not Sicilia DOC.'
        WHEN c.code='T-03' THEN 'Owner-confirmed 2026-09-16: intended designation Sicilia DOC Grecanico Superiore, matching the host-cellar paper label.'
      END,
      CASE WHEN c.code='T-03' THEN 'DOC certification number and date remain separately required before the digital record represents the lot as certified.' END
    ),
    lp.confirmed_by='David Rahamin · owner correction',
    lp.confirmed_at=NOW(6)
WHERE c.code IN ('T-03','M-01');
