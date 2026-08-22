CREATE TABLE IF NOT EXISTS command_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vin TEXT NOT NULL,
    command TEXT NOT NULL,
    request_json TEXT,
    outcome TEXT NOT NULL CHECK(outcome IN ('accepted', 'rejected', 'blocked', 'error')),
    response_code TEXT,
    response_summary TEXT,
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_command_audit_vin_created
    ON command_audit(vin, created_at DESC);
