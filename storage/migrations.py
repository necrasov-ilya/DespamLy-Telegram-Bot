from __future__ import annotations

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        -- moderation events and related tables
        CREATE TABLE IF NOT EXISTS moderation_events (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            chat_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            username TEXT,
            text_hash TEXT,
            text_length INTEGER,
            action TEXT NOT NULL,
            action_confidence REAL,
            filter_keyword_score REAL,
            filter_tfidf_score REAL,
            filter_embedding_score REAL,
            meta_debug TEXT,
            source TEXT NOT NULL DEFAULT 'bot'
        );
        CREATE INDEX IF NOT EXISTS idx_moderation_events_chat_time
            ON moderation_events(chat_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_moderation_events_user_time
            ON moderation_events(user_id, created_at);

        CREATE TABLE IF NOT EXISTS moderation_actions (
            id SERIAL PRIMARY KEY,
            event_id INTEGER NOT NULL,
            performed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            moderator_id BIGINT NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT,
            took_ms INTEGER,
            FOREIGN KEY(event_id) REFERENCES moderation_events(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_moderation_actions_event
            ON moderation_actions(event_id);
        CREATE INDEX IF NOT EXISTS idx_moderation_actions_moderator
            ON moderation_actions(moderator_id, performed_at);

        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            username TEXT,
            first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_whitelisted BOOLEAN NOT NULL DEFAULT FALSE,
            is_banned BOOLEAN NOT NULL DEFAULT FALSE
        );

        CREATE TABLE IF NOT EXISTS log_events (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            level TEXT NOT NULL,
            logger TEXT NOT NULL,
            message TEXT NOT NULL,
            context TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_log_events_level_time
            ON log_events(level, created_at);

        CREATE TABLE IF NOT EXISTS metrics_snapshots (
            id SERIAL PRIMARY KEY,
            period_start TIMESTAMP NOT NULL,
            period TEXT NOT NULL,
            spam_detected INTEGER NOT NULL DEFAULT 0,
            manual_overrides INTEGER NOT NULL DEFAULT 0,
            avg_spam_score REAL,
            embed_failures INTEGER NOT NULL DEFAULT 0,
            UNIQUE(period_start, period)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        2,
        """
        ALTER TABLE moderation_events RENAME COLUMN filter_embedding_score TO filter_pattern_score;
        """,
    ),
    (
        3,
        """
        -- Multi-chat architecture tables
        CREATE TABLE IF NOT EXISTS chat_configs (
            chat_id BIGINT PRIMARY KEY,
            chat_title TEXT,
            chat_type TEXT NOT NULL DEFAULT 'group',
            owner_id BIGINT NOT NULL,
            policy_mode TEXT NOT NULL DEFAULT 'delete_only',
            meta_delete REAL NOT NULL DEFAULT 0.85,
            meta_kick REAL NOT NULL DEFAULT 0.95,
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            whitelist TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_chat_configs_active ON chat_configs(is_active);
        CREATE INDEX IF NOT EXISTS idx_chat_configs_owner ON chat_configs(owner_id);

        CREATE TABLE IF NOT EXISTS chat_daily_stats (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            date DATE NOT NULL,
            messages_processed INTEGER NOT NULL DEFAULT 0,
            spam_detected INTEGER NOT NULL DEFAULT 0,
            messages_deleted INTEGER NOT NULL DEFAULT 0,
            users_banned INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(chat_id) REFERENCES chat_configs(chat_id) ON DELETE CASCADE,
            UNIQUE(chat_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_chat_daily_stats_date ON chat_daily_stats(date);
        """,
    ),
)

__all__ = ["MIGRATIONS"]

