-- The mock portfolio lives in the DB so the deployed API (which has no data/ folder) can read it.
-- Real NSE companies; weights and entry dates are synthetic.
CREATE TABLE holdings (
    company_id   int PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    weight_pct   numeric NOT NULL,
    entry_date   date,
    theme        text,
    size         text,
    is_synthetic boolean NOT NULL DEFAULT true
);

-- Research-set companies (may be outside the portfolio).
CREATE TABLE research_set (
    company_id int PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    role       text
);
