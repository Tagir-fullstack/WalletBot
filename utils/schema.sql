CREATE TABLE IF NOT EXISTS wallet_users (
    user_id BIGINT PRIMARY KEY,
    session JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS wallet_transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES wallet_users(user_id),
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    amount NUMERIC(16,2) NOT NULL CHECK (amount > 0),
    account TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
ALTER TABLE wallet_transactions
    DROP CONSTRAINT IF EXISTS wallet_transactions_account_check;
ALTER TABLE wallet_transactions
    ADD CONSTRAINT wallet_transactions_account_check
    CHECK (account IN ('card', 'cash', 'kaspi', 'halyk'));
CREATE INDEX IF NOT EXISTS wallet_transactions_user_date
    ON wallet_transactions (user_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS wallet_updates (
    update_id BIGINT PRIMARY KEY,
    responses JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
