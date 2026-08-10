CREATE TABLE IF NOT EXISTS charge_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vin TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL,
    end_time TEXT,
    soc_before TEXT,
    soc_after TEXT,
    total_kwhr TEXT,
    location_type TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    watttime_json TEXT,
    imported_at DATETIME DEFAULT (datetime('now')),
    UNIQUE(vin, start_time)
);

CREATE INDEX IF NOT EXISTS idx_charges_vin_start ON charge_sessions(vin, start_time);
