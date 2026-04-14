-- Remove raw_json column (all data already in structured columns + behaviours_json + route_json)
-- SQLite doesn't support DROP COLUMN before 3.35, so we rebuild the table.

ALTER TABLE trips RENAME TO _trips_old;

CREATE TABLE trips (
    id TEXT NOT NULL PRIMARY KEY,
    vin TEXT NOT NULL DEFAULT '',
    category INTEGER NOT NULL DEFAULT 0,
    start_ts DATETIME NOT NULL,
    end_ts DATETIME,
    length_m INTEGER NOT NULL DEFAULT 0,
    duration_s INTEGER NOT NULL DEFAULT 0,
    duration_idle_s INTEGER DEFAULT 0,
    max_speed REAL,
    avg_speed REAL,
    fuel_consumption REAL DEFAULT 0,
    start_lat REAL,
    start_lon REAL,
    end_lat REAL,
    end_lon REAL,
    night_trip BOOLEAN NOT NULL DEFAULT 0,
    length_overspeed INTEGER DEFAULT 0,
    duration_overspeed INTEGER DEFAULT 0,
    length_highway INTEGER DEFAULT 0,
    duration_highway INTEGER DEFAULT 0,
    countries TEXT,
    score_global INTEGER CHECK(score_global IS NULL OR score_global BETWEEN 0 AND 100),
    score_acceleration INTEGER CHECK(score_acceleration IS NULL OR score_acceleration BETWEEN 0 AND 100),
    score_braking INTEGER CHECK(score_braking IS NULL OR score_braking BETWEEN 0 AND 100),
    score_constant_speed INTEGER CHECK(score_constant_speed IS NULL OR score_constant_speed BETWEEN 0 AND 100),
    score_advice INTEGER,
    hdc_ev_time INTEGER DEFAULT 0,
    hdc_ev_distance INTEGER DEFAULT 0,
    hdc_charge_time INTEGER DEFAULT 0,
    hdc_charge_dist INTEGER DEFAULT 0,
    hdc_eco_time INTEGER DEFAULT 0,
    hdc_eco_dist INTEGER DEFAULT 0,
    hdc_power_time INTEGER DEFAULT 0,
    hdc_power_dist INTEGER DEFAULT 0,
    behaviours_json TEXT,
    route_json TEXT,
    imported_at DATETIME DEFAULT (datetime('now'))
);

INSERT INTO trips SELECT
    id, vin, category, start_ts, end_ts, length_m, duration_s, duration_idle_s,
    max_speed, avg_speed, fuel_consumption, start_lat, start_lon, end_lat, end_lon,
    night_trip, length_overspeed, duration_overspeed, length_highway, duration_highway,
    countries, score_global, score_acceleration, score_braking, score_constant_speed,
    score_advice, hdc_ev_time, hdc_ev_distance, hdc_charge_time, hdc_charge_dist,
    hdc_eco_time, hdc_eco_dist, hdc_power_time, hdc_power_dist,
    behaviours_json, route_json, imported_at
FROM _trips_old;

DROP TABLE _trips_old;

CREATE INDEX IF NOT EXISTS idx_trips_start_ts ON trips(start_ts);
CREATE INDEX IF NOT EXISTS idx_trips_vin ON trips(vin);
