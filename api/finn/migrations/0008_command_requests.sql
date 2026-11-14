-- Command-bar model fallback rate limits. Prompts and raw client addresses are never stored.
CREATE TABLE IF NOT EXISTS command_requests (
    id           bigserial PRIMARY KEY,
    requester    text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS command_requests_requester
    ON command_requests (requester, requested_at);
