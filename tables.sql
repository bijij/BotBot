/* Core */

CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.timers (
    id SERIAL,
    created_at TIMESTAMP NOT NULL DEFUALT NOW() AT TIME ZONE 'UTC',
    expires_at TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL,
    data JSONB DEFAULT '{}'::jsonb,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS core.commands (
    message_id BIGINT,
    guild_id BIGINT,
    channel_id BIGINT,
    user_id BIGINT,
    invoked_at TIMESTAMP,
    prefix TEXT,
    command TEXT,
    failed BOOLEAN,
    PRIMARY KEY (message_id)
);

CREATE INDEX IF NOT EXISTS timers_expires_at_idx ON core.commands (expires_at);
CREATE INDEX IF NOT EXISTS timers_event_type_idx ON core.commands (event_type);
CREATE INDEX IF NOT EXISTS commands_guild_id_idx ON core.commands (guild_id);
CREATE INDEX IF NOT EXISTS commands_user_id_idx ON core.commands (user_id);

/* Status Log */

CREATE SCHEMA IF NOT EXISTS logging;

CREATE TYPE logging.status as ENUM ('online', 'offline', 'idle', 'dnd');

CREATE TABLE IF NOT EXISTS logging.opt_in_status (
    user_id BIGINT,
    public BOOLEAN,
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS logging.status_log (
    user_id BIGINT,
    timestamp TIMESTAMP AT TIME ZONE 'UTC',
    status logging.status,
    PRIMARY KEY (user_id, timestamp)
);

CREATE TABLE IF NOT EXISTS logging.message_log (
    channel_id BIGINT,
    message_id BIGINT,
    guild_id BIGINT,
    user_id BIGINT,
    content TEXT,
    PRIMARY KEY (channel_id, message_id)
)

CREATE INDEX IF NOT EXISTS log_user_id_idx ON logging.status_log (user_id);
CREATE INDEX IF NOT EXISTS opt_in_status_user_id_idx ON logging.opt_in_status(user_id);
CREATE INDEX IF NOT EXISTS user_id_idx ON logging.message_log (user_id);