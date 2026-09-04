# Official estate records

The Admin → Documents page is the protected registry for authoritative estate PDFs. Original files are retained unchanged; extracted facts are stored separately with the issuing authority, date, reference, status and operational links.

## Vineyard-area authority

- **Current authoritative registered vineyard surface:** 9,144 m² (0.9144 ha), from the complete 5 September 2025 vineyard-surface register and confirmed current by the owner on 4 September 2026.
- **Italy's new-system extract:** 5,461 m² (0.5461 ha), dated 4 September 2026. It has incomplete coverage and does not supersede the old-system 9,144 m² record. Retain it as reference-only reconciliation evidence until Italy's new system shows the complete holding.
- **New planting pending documentation:** approximately 3,000 m² (0.3000 ha). This is part of the operational planted footprint but is not presented as registered or currently productive.
- **Working planted footprint:** approximately 12,144 m² (1.2144 ha).
- **Expected production:** the pending new planting is expected to become productive in 2027. Current production and yield denominators remain 0.9144 ha; future projections may use approximately 1.2144 ha from 2027 only when explicitly labeled as projected.

Registered area, planted area and productive area are distinct measures. Interfaces and calculations must label which one they use.

## System-wide propagation

All operational consumers use `app/official_facts.py`; SQL and reporting consumers can use `v_official_vineyard_basis` and `v_official_harvest_declarations`. The atlas, parcel records, dashboards, TV data, treatment planning, AI and prediction contexts, reference API, and MCP tools therefore receive the same source-backed values and provenance.

Each atlas parcel exposes its registered vineyard area in hectares and square metres, its official source links, and a reconciliation flag. Whole-vineyard treatment planning uses the approximately 1.2144 ha planted footprint and labels it pending documentation. Historical yield and current-production metrics use the productive denominator for their selected year: 0.9144 ha through 2026 and approximately 1.2144 ha from 2027 unless newer evidence changes the basis.

## Document handling

1. Retain every original PDF unchanged and record its checksum.
2. Extract facts with page-level verification before changing an operational record.
3. Preserve conflicting official documents; mark their coverage and authority rather than deleting or silently overwriting them.
4. Link cadastral and vineyard records to the Atlas, harvest declarations to the vintage/harvest domain, and corporate records to the estate registry.
5. Restrict originals containing personal or corporate identifiers to administrators.
