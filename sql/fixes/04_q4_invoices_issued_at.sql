-- q4, attempt 1 (expected NOT to help - kept as evidence).
-- Tempting: "the query filters on issued_at, so index issued_at". But the
-- 12-month window matches ~62% of invoices. Fetching most of a table through
-- an index means random heap visits per row; a sequential scan is cheaper, and
-- the planner (correctly) keeps choosing it. The slow part of q4 is the 2M-row
-- join and the 1.2M-row text sort, which this index doesn't touch.
CREATE INDEX ix_invoices_issued_at ON invoices (issued_at);
