/* Core */

CREATE SCHEMA IF NOT EXISTS core;

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

CREATE INDEX IF NOT EXISTS commands_guild_id_idx ON core.commands (guild_id);
CREATE INDEX IF NOT EXISTS commands_user_id_idx ON core.commands (user_id);

/* Status Log */

CREATE SCHEMA IF NOT EXISTS status_log;

CREATE TYPE status_log.status as ENUM ('online', 'offline', 'idle', 'dnd');

CREATE TABLE IF NOT EXISTS status_log.opt_in_status (
    user_id BIGINT,
    public BOOLEAN,
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS status_log.log (
    user_id BIGINT,
    timestamp TIMESTAMP AT TIME ZONE 'UTC',
    status status_log.status,
    PRIMARY KEY (user_id, timestamp)
);

CREATE INDEX IF NOT EXISTS log_user_id_idx ON status_log.log (user_id);
CREATE INDEX IF NOT EXISTS opt_in_status_user_id_idx ON status_log.opt_in_status(user_id);