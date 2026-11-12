-- Materialised, render-ready view-models. The read path is a SELECT on this table;
-- the ingest pipeline is the only writer. Keys look like 'brief:24h', 'research:INFY'.
CREATE TABLE views (
    key         text PRIMARY KEY,
    body        jsonb NOT NULL,
    as_of       timestamptz NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
