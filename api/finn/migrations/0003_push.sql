-- Phase 2: classification, bundling, scored brief items, results cards.

CREATE TABLE filing_class (
    filing_id       bigint PRIMARY KEY REFERENCES filings(id) ON DELETE CASCADE,
    category        text NOT NULL,
    sub_type        text,
    base            int NOT NULL,          -- 0–60
    materiality     int,                   -- model's 0–100 when decided by the model
    one_line        text,                  -- ≤ 18 words (enforced in code)
    entities        jsonb NOT NULL DEFAULT '{}'::jsonb,
    needs_deep_read boolean NOT NULL DEFAULT false,
    decided_by      text NOT NULL CHECK (decided_by IN ('rules', 'llm')),
    model           text,
    prompt_version  text,
    reason          text,
    classified_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX filing_class_category ON filing_class (category);

ALTER TABLE filings ADD COLUMN bundle_id bigint;
ALTER TABLE filings ADD COLUMN dup_of bigint REFERENCES filings(id) ON DELETE SET NULL;

-- Computed results cards (one per company, period, basis). Numbers come from XBRL facts.
CREATE TABLE results_cards (
    company_id   int  NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    period_end   date NOT NULL,
    basis        text NOT NULL,
    card         jsonb NOT NULL,
    verified     boolean NOT NULL,
    issues       text[] NOT NULL DEFAULT '{}',
    computed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, period_end, basis)
);

-- Materialised brief items: one per filing or bundle, with the score broken down.
CREATE TABLE brief_items (
    id           text PRIMARY KEY,            -- 'f<filing_id>' or 'b<bundle_id>'
    company_id   int NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    ts_ist       timestamptz NOT NULL,
    category     text NOT NULL,
    sub_type     text,
    kind         text NOT NULL,               -- 'results' | 'mgmt' | 'event' | 'line' | 'filing'
    score        int NOT NULL,
    components   jsonb NOT NULL,
    filing_ids   bigint[] NOT NULL,
    body         jsonb NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX brief_items_ts ON brief_items (ts_ist DESC);
