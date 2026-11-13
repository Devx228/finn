-- Where a document came from: the exchange feed (default) or the company's IR site, downloaded
-- by hand when the exchange was unavailable. `url` is always the original for the citation link.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'NSE';
