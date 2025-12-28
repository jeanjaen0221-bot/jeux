CREATE TABLE IF NOT EXISTS nodes (
  id               UUID PRIMARY KEY,
  node_type        TEXT NOT NULL,
  name             TEXT NOT NULL,
  parent_id        UUID NULL REFERENCES nodes(id) ON DELETE CASCADE,
  slug             TEXT NULL,
  chunk_id         TEXT NULL,
  attrs            JSONB NOT NULL DEFAULT '{}',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_chunk ON nodes(chunk_id);
CREATE INDEX IF NOT EXISTS idx_nodes_gin ON nodes USING GIN (attrs);

CREATE TABLE IF NOT EXISTS links (
  id               UUID PRIMARY KEY,
  src_id           UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  dst_id           UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  link_type        TEXT NOT NULL,
  weight           REAL NULL,
  attrs            JSONB NOT NULL DEFAULT '{}',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_links_src ON links(src_id);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst_id);
CREATE INDEX IF NOT EXISTS idx_links_type ON links(link_type);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id         TEXT PRIMARY KEY,
  scope_type       TEXT NOT NULL,
  scope_node_id    UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  status           TEXT NOT NULL DEFAULT 'pending',
  attrs            JSONB NOT NULL DEFAULT '{}',
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
