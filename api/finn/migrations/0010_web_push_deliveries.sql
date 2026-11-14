-- Successful automatic deliveries, so a device receives each stored Now card only once.
CREATE TABLE IF NOT EXISTS web_push_deliveries (
    subscription_token text NOT NULL REFERENCES web_push_subscriptions(token) ON DELETE CASCADE,
    item_id             text NOT NULL,
    sent_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (subscription_token, item_id)
);
