from __future__ import annotations

import contextlib
import json
from dataclasses import asdict
from datetime import datetime, date
from threading import RLock
from typing import Any, Iterable, Mapping, Sequence

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as Connection

from .interfaces import (
    ChatConfig,
    ChatConfigInput,
    ChatConfigStore,
    ChatDailyStats,
    ChatDailyStatsInput,
    ChatStatsStore,
    MetricsSnapshot,
    MetricsStore,
    ModerationAction,
    ModerationActionInput,
    ModerationEvent,
    ModerationEventInput,
    ModerationStore,
    SettingsStore,
    UserProfile,
    UserStore,
)


class Storage:
    """
    Entry point for interacting with PostgreSQL-backed repositories.
    Uses connection pool and thread-safe operations.
    """

    def __init__(self, *, conn: Connection):
        self._conn = conn
        self._lock = RLock()
        self.events: ModerationStore = _ModerationStore(conn, self._lock)
        self.users: UserStore = _UserStore(conn, self._lock)
        self.metrics: MetricsStore = _MetricsStore(conn, self._lock)
        self.settings: SettingsStore = _SettingsStore(conn, self._lock)
        self.chat_configs: ChatConfigStore = _ChatConfigStore(conn, self._lock)
        self.chat_stats: ChatStatsStore = _ChatStatsStore(conn, self._lock)
        self.logs = _LogStore(conn, self._lock)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class _PostgresRepoBase:
    def __init__(self, conn: Connection, lock: RLock):
        self._conn = conn
        self._lock = lock

    @contextlib.contextmanager
    def _cursor(self) -> Iterable[psycopg2.extras.RealDictCursor]:
        with self._lock:
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()


class _ModerationStore(_PostgresRepoBase, ModerationStore):
    def record_event(self, data: ModerationEventInput) -> int:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO moderation_events (
                    chat_id, message_id, user_id, username, text_hash, text_length,
                    action, action_confidence, filter_keyword_score,
                    filter_tfidf_score, filter_pattern_score, meta_debug, source
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    data.chat_id,
                    data.message_id,
                    data.user_id,
                    data.username,
                    data.text_hash,
                    data.text_length,
                    data.action,
                    data.action_confidence,
                    data.filter_keyword_score,
                    data.filter_tfidf_score,
                    data.filter_pattern_score,
                    data.meta_debug,
                    data.source,
                ),
            )
            result = cur.fetchone()
            return int(result["id"])

    def fetch_recent(self, limit: int = 100) -> Sequence[ModerationEvent]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT
                    id, created_at, chat_id, message_id, user_id, username, text_hash,
                    text_length, action, action_confidence, filter_keyword_score,
                    filter_tfidf_score, filter_pattern_score, meta_debug, source
                FROM moderation_events
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

        return [
            ModerationEvent(
                id=row["id"],
                created_at=row["created_at"],
                chat_id=row["chat_id"],
                message_id=row["message_id"],
                user_id=row["user_id"],
                username=row["username"],
                text_hash=row["text_hash"],
                text_length=row["text_length"],
                action=row["action"],
                action_confidence=row["action_confidence"],
                filter_keyword_score=row["filter_keyword_score"],
                filter_tfidf_score=row["filter_tfidf_score"],
                filter_pattern_score=row["filter_pattern_score"],
                meta_debug=row["meta_debug"],
                source=row["source"],
            )
            for row in rows
        ]

    def record_action(self, data: ModerationActionInput) -> int:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO moderation_actions (
                    event_id, moderator_id, decision, reason, took_ms
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    data.event_id,
                    data.moderator_id,
                    data.decision,
                    data.reason,
                    data.took_ms,
                ),
            )
            result = cur.fetchone()
            return int(result["id"])

    def fetch_actions(self, event_id: int) -> Sequence[ModerationAction]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT
                    id, event_id, performed_at, moderator_id, decision, reason, took_ms
                FROM moderation_actions
                WHERE event_id = %s
                ORDER BY performed_at ASC
                """,
                (event_id,),
            )
            rows = cur.fetchall()

        return [
            ModerationAction(
                id=row["id"],
                event_id=row["event_id"],
                performed_at=row["performed_at"],
                moderator_id=row["moderator_id"],
                decision=row["decision"],
                reason=row["reason"],
                took_ms=row["took_ms"],
            )
            for row in rows
        ]


class _UserStore(_PostgresRepoBase, UserStore):
    def upsert(
        self,
        telegram_id: int,
        *,
        username: str | None,
        is_whitelisted: bool | None = None,
        is_banned: bool | None = None,
    ) -> None:
        with self._cursor() as cur:
            # Build dynamic SET clause
            updates = ["username = EXCLUDED.username", "last_seen_at = CURRENT_TIMESTAMP"]
            if is_whitelisted is not None:
                updates.append(f"is_whitelisted = {is_whitelisted}")
            if is_banned is not None:
                updates.append(f"is_banned = {is_banned}")

            set_clause = ", ".join(updates)

            cur.execute(
                f"""
                INSERT INTO users(telegram_id, username, is_whitelisted, is_banned)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    {set_clause}
                """,
                (
                    telegram_id,
                    username,
                    is_whitelisted if is_whitelisted is not None else False,
                    is_banned if is_banned is not None else False,
                ),
            )

    def touch(self, telegram_id: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET last_seen_at = CURRENT_TIMESTAMP
                WHERE telegram_id = %s
                """,
                (telegram_id,),
            )

    def fetch(self, telegram_id: int) -> UserProfile | None:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT telegram_id, username, first_seen_at, last_seen_at,
                       is_whitelisted, is_banned
                FROM users
                WHERE telegram_id = %s
                """,
                (telegram_id,),
            )
            row = cur.fetchone()

        if not row:
            return None

        return UserProfile(
            telegram_id=row["telegram_id"],
            username=row["username"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            is_whitelisted=row["is_whitelisted"],
            is_banned=row["is_banned"],
        )


class _MetricsStore(_PostgresRepoBase, MetricsStore):
    def record_snapshot(self, snapshot: MetricsSnapshot) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO metrics_snapshots (
                    period_start, period, spam_detected, manual_overrides,
                    avg_spam_score, embed_failures
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(period_start, period) DO UPDATE SET
                    spam_detected = EXCLUDED.spam_detected,
                    manual_overrides = EXCLUDED.manual_overrides,
                    avg_spam_score = EXCLUDED.avg_spam_score,
                    embed_failures = EXCLUDED.embed_failures
                """,
                (
                    snapshot.period_start,
                    snapshot.period,
                    snapshot.spam_detected,
                    snapshot.manual_overrides,
                    snapshot.avg_spam_score,
                    snapshot.embed_failures,
                ),
            )

    def fetch_recent(self, limit: int = 30) -> Sequence[MetricsSnapshot]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT period_start, period, spam_detected, manual_overrides,
                       avg_spam_score, embed_failures
                FROM metrics_snapshots
                ORDER BY period_start DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

        return [
            MetricsSnapshot(
                period_start=row["period_start"],
                period=row["period"],
                spam_detected=row["spam_detected"],
                manual_overrides=row["manual_overrides"],
                avg_spam_score=row["avg_spam_score"],
                embed_failures=row["embed_failures"],
            )
            for row in rows
        ]


class _SettingsStore(_PostgresRepoBase, SettingsStore):
    def load_overrides(self) -> Mapping[str, str]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT key, value FROM settings ORDER BY key ASC",
            )
            rows = cur.fetchall()

        return {row["key"]: row["value"] for row in rows}

    def upsert(self, key: str, value: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings(key, value)
                VALUES (%s, %s)
                ON CONFLICT(key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    def remove(self, key: str) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM settings WHERE key = %s", (key,))


class _ChatConfigStore(_PostgresRepoBase, ChatConfigStore):
    def get_by_chat_id(self, chat_id: int) -> ChatConfig | None:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT chat_id, chat_title, chat_type, owner_id, policy_mode,
                       meta_delete, meta_kick, is_active, whitelist, moderator_channel_id,
                       created_at, updated_at
                FROM chat_configs
                WHERE chat_id = %s
                """,
                (chat_id,),
            )
            row = cur.fetchone()

        if not row:
            return None

        return ChatConfig(
            chat_id=row["chat_id"],
            chat_title=row["chat_title"],
            chat_type=row["chat_type"],
            owner_id=row["owner_id"],
            policy_mode=row["policy_mode"],
            meta_delete=row["meta_delete"],
            meta_kick=row["meta_kick"],
            is_active=row["is_active"],
            whitelist=json.loads(row["whitelist"]) if row["whitelist"] else None,
            moderator_channel_id=row["moderator_channel_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_by_owner_id(self, owner_id: int) -> Sequence[ChatConfig]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT chat_id, chat_title, chat_type, owner_id, policy_mode,
                       meta_delete, meta_kick, is_active, whitelist, moderator_channel_id,
                       created_at, updated_at
                FROM chat_configs
                WHERE owner_id = %s
                ORDER BY created_at DESC
                """,
                (owner_id,),
            )
            rows = cur.fetchall()

        return [
            ChatConfig(
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
                chat_type=row["chat_type"],
                owner_id=row["owner_id"],
                policy_mode=row["policy_mode"],
                meta_delete=row["meta_delete"],
                meta_kick=row["meta_kick"],
                is_active=row["is_active"],
                whitelist=json.loads(row["whitelist"]) if row["whitelist"] else None,
                moderator_channel_id=row["moderator_channel_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
    
    def get_by_moderator_channel_id(self, channel_id: int) -> Sequence[ChatConfig]:
        """Найти все чаты, использующие этот канал как модераторский."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT chat_id, chat_title, chat_type, owner_id, policy_mode,
                       meta_delete, meta_kick, is_active, whitelist, moderator_channel_id,
                       created_at, updated_at
                FROM chat_configs
                WHERE moderator_channel_id = %s
                """,
                (channel_id,),
            )
            rows = cur.fetchall()

        return [
            ChatConfig(
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
                chat_type=row["chat_type"],
                owner_id=row["owner_id"],
                policy_mode=row["policy_mode"],
                meta_delete=row["meta_delete"],
                meta_kick=row["meta_kick"],
                is_active=row["is_active"],
                whitelist=json.loads(row["whitelist"]) if row["whitelist"] else None,
                moderator_channel_id=row["moderator_channel_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
    
    def was_moderator_channel(self, channel_id: int) -> bool:
        """Проверить, использовался ли этот ID как модераторский канал раньше."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) as count
                FROM chat_configs
                WHERE moderator_channel_id = %s
                """,
                (channel_id,),
            )
            row = cur.fetchone()
            return row["count"] > 0 if row else False

    def upsert(self, config: ChatConfigInput) -> None:
        whitelist_json = json.dumps(config.whitelist) if config.whitelist else None

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_configs(
                    chat_id, chat_title, chat_type, owner_id, policy_mode,
                    meta_delete, meta_kick, is_active, whitelist, moderator_channel_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_title = EXCLUDED.chat_title,
                    chat_type = EXCLUDED.chat_type,
                    owner_id = EXCLUDED.owner_id,
                    policy_mode = EXCLUDED.policy_mode,
                    meta_delete = EXCLUDED.meta_delete,
                    meta_kick = EXCLUDED.meta_kick,
                    is_active = EXCLUDED.is_active,
                    whitelist = EXCLUDED.whitelist,
                    moderator_channel_id = EXCLUDED.moderator_channel_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    config.chat_id,
                    config.chat_title,
                    config.chat_type,
                    config.owner_id,
                    config.policy_mode,
                    config.meta_delete,
                    config.meta_kick,
                    config.is_active,
                    whitelist_json,
                    config.moderator_channel_id,
                ),
            )

    def update(self, chat_id: int, **updates) -> None:
        if not updates:
            return

        # Special handling for whitelist
        if "whitelist" in updates and updates["whitelist"] is not None:
            updates["whitelist"] = json.dumps(updates["whitelist"])

        set_clauses = [f"{key} = %s" for key in updates]
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        set_clause = ", ".join(set_clauses)

        with self._cursor() as cur:
            cur.execute(
                f"""
                UPDATE chat_configs
                SET {set_clause}
                WHERE chat_id = %s
                """,
                (*updates.values(), chat_id),
            )

    def delete(self, chat_id: int) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM chat_configs WHERE chat_id = %s", (chat_id,))


class _ChatStatsStore(_PostgresRepoBase, ChatStatsStore):
    def increment(
        self,
        chat_id: int,
        date: datetime,
        *,
        messages_processed: int = 0,
        spam_detected: int = 0,
        messages_deleted: int = 0,
        users_banned: int = 0,
    ) -> None:
        date_only = date.date() if isinstance(date, datetime) else date

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_daily_stats(
                    chat_id, date, messages_processed, spam_detected,
                    messages_deleted, users_banned
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(chat_id, date) DO UPDATE SET
                    messages_processed = chat_daily_stats.messages_processed + EXCLUDED.messages_processed,
                    spam_detected = chat_daily_stats.spam_detected + EXCLUDED.spam_detected,
                    messages_deleted = chat_daily_stats.messages_deleted + EXCLUDED.messages_deleted,
                    users_banned = chat_daily_stats.users_banned + EXCLUDED.users_banned
                """,
                (
                    chat_id,
                    date_only,
                    messages_processed,
                    spam_detected,
                    messages_deleted,
                    users_banned,
                ),
            )

    def get_stats(self, chat_id: int, days: int = 7) -> Sequence[ChatDailyStats]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, chat_id, date, messages_processed, spam_detected,
                       messages_deleted, users_banned
                FROM chat_daily_stats
                WHERE chat_id = %s AND date >= CURRENT_DATE - INTERVAL '%s days'
                ORDER BY date DESC
                """,
                (chat_id, days),
            )
            rows = cur.fetchall()

        return [
            ChatDailyStats(
                id=row["id"],
                chat_id=row["chat_id"],
                date=row["date"],
                messages_processed=row["messages_processed"],
                spam_detected=row["spam_detected"],
                messages_deleted=row["messages_deleted"],
                users_banned=row["users_banned"],
            )
            for row in rows
        ]


class _LogStore(_PostgresRepoBase):
    def write(self, level: str, logger: str, message: str, context: dict | None = None) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO log_events(level, logger, message, context)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    level,
                    logger,
                    message,
                    json.dumps(context) if context else None,
                ),
            )
