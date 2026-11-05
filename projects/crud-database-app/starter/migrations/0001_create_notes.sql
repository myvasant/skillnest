-- 0001: the notes table.
--
-- AUTOINCREMENT guarantees that an id is never handed out twice, even after the newest note is
-- deleted (a plain INTEGER PRIMARY KEY may reuse the largest deleted id, so an old link or cache
-- entry could suddenly point at a different note).
-- Timestamps are ISO-8601 text in UTC, e.g. 2026-01-01T09:00:00.000000+00:00; that format also
-- sorts correctly as text.
-- The CHECK constraints repeat the API's validation rules, so bad data cannot get in by another route
-- (a script, a future endpoint, someone at the sqlite3 prompt).
CREATE TABLE notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    body       TEXT NOT NULL DEFAULT '' CHECK (length(body) <= 10000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
