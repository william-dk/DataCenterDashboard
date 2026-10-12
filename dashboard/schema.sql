-- Foundation v0.1. Validated with SQLite; adapt types explicitly for DuckDB/PostgreSQL.
PRAGMA foreign_keys = ON;
CREATE TABLE layers (layer_id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE subsectors (subsector_id TEXT PRIMARY KEY, layer_id TEXT NOT NULL REFERENCES layers, name TEXT NOT NULL);
CREATE TABLE companies (company_id TEXT PRIMARY KEY, name TEXT NOT NULL, identity_status TEXT NOT NULL);
CREATE TABLE securities (
  security_id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies,
  ticker TEXT NOT NULL, exchange TEXT NOT NULL, currency TEXT NOT NULL,
  valid_from TEXT NOT NULL, valid_to TEXT, verified_source_id TEXT REFERENCES sources
);
CREATE TABLE company_exposures (
  company_id TEXT NOT NULL REFERENCES companies, subsector_id TEXT NOT NULL REFERENCES subsectors,
  segment TEXT NOT NULL, geography TEXT NOT NULL, as_of TEXT NOT NULL,
  source_id TEXT REFERENCES sources, locator TEXT, status TEXT NOT NULL,
  PRIMARY KEY (company_id, subsector_id, segment, geography, as_of)
);
CREATE TABLE sources (
  source_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
  source_type TEXT NOT NULL, published_at TEXT, retrieved_at TEXT NOT NULL,
  local_path TEXT, license_note TEXT, content_hash TEXT
);
CREATE TABLE metrics (
  metric_id TEXT PRIMARY KEY, definition TEXT NOT NULL, unit TEXT NOT NULL,
  value_type TEXT NOT NULL CHECK (value_type IN ('numeric','date','text'))
);
CREATE TABLE observations (
  observation_id TEXT PRIMARY KEY, company_id TEXT REFERENCES companies,
  entity_scope TEXT NOT NULL, segment TEXT NOT NULL, geography TEXT NOT NULL,
  metric_id TEXT NOT NULL REFERENCES metrics, value_numeric REAL, value_text TEXT,
  raw_value TEXT, unit TEXT NOT NULL, currency TEXT,
  period_start TEXT, period_end TEXT NOT NULL, period_type TEXT NOT NULL,
  published_at TEXT, available_at TEXT NOT NULL, retrieved_at TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources, locator TEXT NOT NULL,
  transformation TEXT, quality_status TEXT NOT NULL, missing_reason TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  supersedes_id TEXT REFERENCES observations,
  CHECK (NOT (value_numeric IS NOT NULL AND value_text IS NOT NULL)),
  CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL OR missing_reason IS NOT NULL),
  UNIQUE (entity_scope, segment, geography, metric_id, period_end, period_type, source_id, locator, revision)
);
CREATE INDEX observations_asof ON observations (metric_id, period_end, available_at);
CREATE TABLE assumptions (
  assumption_id TEXT NOT NULL, version INTEGER NOT NULL CHECK (version > 0),
  company_id TEXT NOT NULL REFERENCES companies, metric_id TEXT NOT NULL REFERENCES metrics,
  scenario TEXT NOT NULL CHECK (scenario IN ('bull','base','bear','other')),
  value_numeric REAL, value_text TEXT, unit TEXT NOT NULL, rationale TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','review','approved','rejected')),
  approved_by TEXT, approved_at TEXT,
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  PRIMARY KEY (assumption_id, version)
);
CREATE TABLE theses (
  thesis_id TEXT NOT NULL, version INTEGER NOT NULL CHECK (version > 0),
  company_id TEXT NOT NULL REFERENCES companies, original_version INTEGER NOT NULL,
  content_json TEXT NOT NULL, model_version TEXT, rationale TEXT NOT NULL,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','review','approved','rejected')),
  approved_by TEXT, approved_at TEXT,
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  PRIMARY KEY (thesis_id, version)
);
CREATE TABLE events (
  event_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources,
  category TEXT NOT NULL, headline TEXT NOT NULL, locator TEXT NOT NULL,
  published_at TEXT, available_at TEXT NOT NULL, retrieved_at TEXT NOT NULL,
  extracted_claim TEXT NOT NULL, verification_status TEXT NOT NULL,
  source_event_key TEXT NOT NULL, UNIQUE (source_id, source_event_key)
);
CREATE TABLE event_entities (
  event_id TEXT NOT NULL REFERENCES events, company_id TEXT NOT NULL REFERENCES companies,
  PRIMARY KEY (event_id, company_id)
);
CREATE TABLE event_subsectors (
  event_id TEXT NOT NULL REFERENCES events, subsector_id TEXT NOT NULL REFERENCES subsectors,
  PRIMARY KEY (event_id, subsector_id)
);
CREATE TABLE review_queue (
  review_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events,
  affected_debate TEXT NOT NULL, affected_driver TEXT NOT NULL,
  impact_proposal TEXT NOT NULL, materiality_reason TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('proposed','evidence_checked','approved','rejected','context_only')),
  reviewed_by TEXT, reviewed_at TEXT,
  CHECK (status NOT IN ('approved','rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE TABLE ingestion_runs (
  run_id TEXT PRIMARY KEY, adapter TEXT NOT NULL, started_at TEXT NOT NULL,
  completed_at TEXT, status TEXT NOT NULL CHECK (status IN ('running','success','partial','failed')),
  records_added INTEGER NOT NULL DEFAULT 0, error_details TEXT
);
-- Access control, append-only enforcement, finite values, metric-specific validation,
-- hashes, freshness policy and materiality gates belong to implementation layers.
