-- 0002: tags, and which notes carry them (a many-to-many relationship).
--
-- Each tag name is stored once in `tags`; `note_tags` links notes to tags.
-- ON DELETE CASCADE: deleting a note (or a tag) deletes its links automatically. SQLite only enforces
-- this when the connection has run PRAGMA foreign_keys = ON (see connect()).
-- `position` keeps tags in the order the client sent them: rows in a table have no order of their own.
CREATE TABLE tags (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE note_tags (
    note_id  INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (note_id, tag_id)
);
