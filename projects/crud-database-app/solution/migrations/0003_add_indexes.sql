-- 0003: indexes for the queries the repository runs.
--
-- "Tags of a note" is served by note_tags' primary key, which starts with note_id.
-- "Notes with tag X" looks rows up by tag_id, which is the SECOND column of that key, so without this
-- index SQLite would scan the whole table. tags.name needs no index: UNIQUE already created one.
-- Check with: EXPLAIN QUERY PLAN SELECT note_id FROM note_tags WHERE tag_id = 1;
CREATE INDEX idx_note_tags_tag_id ON note_tags (tag_id);
