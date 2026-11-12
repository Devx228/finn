-- Phase 3: the Network. Every network table carries tenant_id (one investor = one tenant).
-- Contacts are synthetic (is_synthetic = true, labelled in the UI). Public figures come only
-- from exchange filings, with the source URL.

CREATE TABLE orgs (
    id              serial PRIMARY KEY,
    canonical_name  text NOT NULL UNIQUE,
    aliases         text[] NOT NULL DEFAULT '{}',
    company_id      int REFERENCES companies(id) ON DELETE SET NULL,
    industry        text,
    kind            text NOT NULL DEFAULT 'company',  -- company | institution | regulator | fund
    unreviewed      boolean NOT NULL DEFAULT false
);

CREATE TABLE persons (
    id            serial PRIMARY KEY,
    tenant_id     int,                                -- NULL for public figures (shared)
    kind          text NOT NULL CHECK (kind IN ('contact', 'public_figure', 'investor')),
    full_name     text NOT NULL,
    name_norm     text NOT NULL,
    headline      text,
    city          text,
    is_synthetic  boolean NOT NULL,
    source        text,
    source_url    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    refreshed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX persons_name_norm ON persons (name_norm);

CREATE TABLE employments (
    id          serial PRIMARY KEY,
    person_id   int NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    org_id      int NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    title       text,
    function    text,          -- finance | operations | sales | strategy | legal-compliance |
                               -- R&D-technical | treasury-credit | IR | HR | general-management
    seniority   int,           -- 1–5
    start_ym    date,
    end_ym      date,          -- NULL = current
    source_url  text
);
CREATE INDEX employments_org ON employments (org_id);

CREATE TABLE educations (
    id                  serial PRIMARY KEY,
    person_id           int NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    institution_org_id  int NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    degree              text,
    field               text,
    start_y             int,
    end_y               int
);

CREATE TABLE relationships (
    tenant_id          int NOT NULL,
    contact_id         int NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    how_known          text NOT NULL,
    since_ym           date,
    last_contact_date  date,
    interactions_24m   int NOT NULL DEFAULT 0,
    closeness          int NOT NULL,     -- 1–5
    notes              text,
    PRIMARY KEY (tenant_id, contact_id)
);

CREATE TABLE meetings (
    id          serial PRIMARY KEY,
    tenant_id   int NOT NULL,
    date        date NOT NULL,
    company_id  int REFERENCES companies(id) ON DELETE SET NULL,
    person_ids  int[] NOT NULL DEFAULT '{}',
    notes       text,
    tags        text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE expertise (
    person_id  int NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    theme      text NOT NULL,
    score      numeric NOT NULL,
    evidence   text,
    PRIMARY KEY (person_id, theme)
);

CREATE TABLE org_relations (
    a           int NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    b           int NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('peer', 'supplier', 'customer', 'parent', 'subsidiary')),
    source      text NOT NULL,
    confidence  numeric NOT NULL DEFAULT 1,
    PRIMARY KEY (a, b, kind)
);

-- A person named in a filing (resolved to a public figure), with the match evidence.
CREATE TABLE person_mentions (
    filing_id         bigint NOT NULL REFERENCES filings(id) ON DELETE CASCADE,
    person_id         int NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    role              text,
    event             text,          -- appointment | resignation | cessation | re-designation
    effective_date    date,
    match_confidence  numeric NOT NULL,
    evidence          jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (filing_id, person_id)
);
