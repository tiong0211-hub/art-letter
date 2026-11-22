CREATE TABLE IF NOT EXISTS comments (
  id          TEXT PRIMARY KEY,
  issue       TEXT NOT NULL,
  parent_id   TEXT,
  nickname    TEXT NOT NULL,
  body        TEXT NOT NULL,
  owner_hash  TEXT,
  ip_hash     TEXT,
  created_at  TEXT NOT NULL,
  deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS comments_issue_created ON comments (issue, created_at);
CREATE INDEX IF NOT EXISTS comments_ip_created ON comments (ip_hash, created_at);
