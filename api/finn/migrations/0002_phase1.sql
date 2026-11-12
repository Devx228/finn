-- Phase 1: companies, prices, filings, documents, structured financials, LLM cache + ledger.
-- Market data is public and tenant-less. Network tables (with tenant_id) arrive in Phase 3.

CREATE TABLE companies (
    id            serial PRIMARY KEY,
    nse_symbol    text NOT NULL UNIQUE,
    kind          text NOT NULL DEFAULT 'equity' CHECK (kind IN ('equity', 'index')),
    isin          text,
    name          text NOT NULL,
    series        text,
    listed_on     date,
    industry      text,            -- as NSE labels it (smIndustry)
    fin_format    text,            -- 'indas' | 'bank' | 'nbfc' (from NSE's results flag)
    is_financial  boolean NOT NULL DEFAULT false,
    mcap_cr       numeric,         -- computed: shares (from XBRL) x last close
    mcap_bucket   text,            -- 'large' | 'mid' | 'small' (approximate, see DECISIONS)
    aliases       text[] NOT NULL DEFAULT '{}',
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE prices (
    company_id  int  NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    date        date NOT NULL,
    open        numeric, high numeric, low numeric, close numeric, adj_close numeric,
    volume      bigint,
    PRIMARY KEY (company_id, date)
);

-- One row per exchange announcement. PDF text is fetched lazily (only when a stage needs it).
CREATE TABLE filings (
    id              bigserial PRIMARY KEY,
    company_id      int NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    exchange        text NOT NULL DEFAULT 'NSE',
    exch_id         text NOT NULL,          -- NSE seq_id
    ts_ist          timestamptz NOT NULL,
    exch_category   text,                   -- NSE 'desc'
    subject         text,                   -- NSE 'attchmntText'
    pdf_url         text,
    pdf_size_label  text,
    pdf_sha256      text,
    n_pages         int,
    text_pages      jsonb,                  -- ["page 1 text", ...] once fetched
    is_scanned      boolean,
    text_fetched_at timestamptz,
    raw             jsonb NOT NULL,         -- the exchange row as received
    UNIQUE (exchange, exch_id)
);
CREATE INDEX filings_company_ts ON filings (company_id, ts_ist DESC);
CREATE INDEX filings_ts ON filings (ts_ist DESC);

-- Fundamentals documents: annual reports and concall transcripts (links now, text in Phase 4).
CREATE TABLE documents (
    id          bigserial PRIMARY KEY,
    company_id  int NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('annual_report', 'transcript', 'presentation')),
    period      text,                       -- 'FY2026' for ARs; quarter label for transcripts
    filed_at    timestamptz,
    url         text NOT NULL UNIQUE,
    size_label  text,
    sha256      text,
    n_pages     int,
    pages       jsonb,
    fetched_at  timestamptz,
    filing_id   bigint REFERENCES filings(id) ON DELETE SET NULL
);
CREATE INDEX documents_company_kind ON documents (company_id, kind);

-- Structured results filings (XBRL), both NSE eras.
CREATE TABLE fin_filings (
    id            bigserial PRIMARY KEY,
    company_id    int NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    source        text NOT NULL CHECK (source IN ('nse_cfr', 'nse_integrated')),
    basis         text NOT NULL CHECK (basis IN ('consolidated', 'standalone')),
    fmt           text,                     -- NSE format flag: N (Ind AS), B (bank), F (NBFC)
    period_start  date,
    period_end    date NOT NULL,
    audited       boolean,
    filed_at      timestamptz,
    xbrl_url      text NOT NULL UNIQUE,
    rounding      text,                     -- 'Lakhs' | 'Crores' | ... as stated in the filing
    n_facts       int,
    parsed_at     timestamptz,
    parse_error   text
);
CREATE INDEX fin_filings_company ON fin_filings (company_id, basis, period_end);

-- Every numeric fact as reported (absolute INR for monetary items). dims = '' for plain facts;
-- dimensioned facts (segments) carry 'Axis=Member'.
CREATE TABLE fin_facts (
    fin_filing_id  bigint NOT NULL REFERENCES fin_filings(id) ON DELETE CASCADE,
    concept        text NOT NULL,
    dims           text NOT NULL DEFAULT '',
    period_start   date,                    -- NULL for instants (balance sheet)
    period_end     date NOT NULL,
    value          numeric NOT NULL,
    unit           text
);
CREATE UNIQUE INDEX fin_facts_key ON fin_facts
    (fin_filing_id, concept, dims, period_end, period_start) NULLS NOT DISTINCT;
CREATE INDEX fin_facts_concept ON fin_facts (concept, period_end);

-- LLM content-hash cache: a document is never read by a model twice.
CREATE TABLE llm_cache (
    key         text PRIMARY KEY,           -- sha256(tier, prompt_version, input_hash)
    tier        text NOT NULL,
    provider    text NOT NULL,
    model       text NOT NULL,
    response    jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Cost ledger: every call, including cache hits. No personal data in here.
CREATE TABLE llm_calls (
    id              bigserial PRIMARY KEY,
    ts              timestamptz NOT NULL DEFAULT now(),
    tier            text NOT NULL,
    provider        text,
    model           text,
    purpose         text NOT NULL,
    input_tokens    int,
    output_tokens   int,
    cache_hit       boolean NOT NULL,
    latency_ms      int,
    list_price_usd  numeric,
    ok              boolean NOT NULL,
    error           text
);
CREATE INDEX llm_calls_ts ON llm_calls (ts DESC);

-- Ingest runs, for "data as of" and the gate's row counts.
CREATE TABLE ingest_runs (
    id          bigserial PRIMARY KEY,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    host        text,
    steps       jsonb NOT NULL DEFAULT '{}'::jsonb,
    ok          boolean,
    error       text
);
