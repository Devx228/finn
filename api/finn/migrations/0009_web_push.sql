-- Browser push subscriptions. The endpoint and keys are opaque browser-issued credentials;
-- no prompt, notification text or raw client address is stored.
CREATE TABLE IF NOT EXISTS web_push_subscriptions (
    token        text PRIMARY KEY,
    endpoint     text NOT NULL UNIQUE,
    subscription jsonb NOT NULL,
    requester    text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    disabled_at  timestamptz
);

CREATE TABLE IF NOT EXISTS web_push_test_requests (
    id           bigserial PRIMARY KEY,
    requester    text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS web_push_test_requester
    ON web_push_test_requests (requester, requested_at);

