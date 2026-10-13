-- Keep the historical Grenache evidence card consistent with Wendy's current
-- notebook reconciliation. Purchased fruit remains excluded from estate yield.

UPDATE vintage_summaries
SET reconciliation_note='2026 Grenache production fruit: 399.25 kg estate-grown harvest plus 1,078.00 kg purchased fruit from the owner-supplied "Steph Yim''s 1200 plot" source wording = 1,477.25 kg total fruit received. Wendy''s current notebook records 61 purchased-fruit crates. Purchased fruit remains excluded from estate vineyard yield/completion calculations.'
WHERE vintage_year=2026 AND LOWER(variety_name)='grenache';
