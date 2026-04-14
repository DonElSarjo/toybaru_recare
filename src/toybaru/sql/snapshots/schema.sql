CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vin TEXT NOT NULL DEFAULT '',
    timestamp DATETIME NOT NULL,
    soc INTEGER CHECK(soc IS NULL OR soc BETWEEN 0 AND 100),
    range_km REAL,
    range_ac_km REAL,
    odometer REAL,
    charging_status TEXT CHECK(charging_status IS NULL OR charging_status IN ('none', 'charging', 'connected')),
    latitude REAL,
    longitude REAL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_vin_ts ON snapshots(vin, timestamp);
