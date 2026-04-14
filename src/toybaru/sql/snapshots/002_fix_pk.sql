-- Fix: change PK from timestamp to autoincrement id

ALTER TABLE snapshots RENAME TO _snapshots_old;

CREATE TABLE snapshots (
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

INSERT INTO snapshots (vin, timestamp, soc, range_km, range_ac_km, odometer, charging_status, latitude, longitude)
SELECT COALESCE(vin, ''), timestamp, soc, range_km, range_ac_km, odometer, charging_status, latitude, longitude
FROM _snapshots_old;

DROP TABLE _snapshots_old;

CREATE INDEX IF NOT EXISTS idx_snapshots_vin_ts ON snapshots(vin, timestamp);
