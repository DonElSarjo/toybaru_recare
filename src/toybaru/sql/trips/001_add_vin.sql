-- Add vin column if missing (for DBs created before multi-vehicle support)
ALTER TABLE trips ADD COLUMN vin TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_trips_vin ON trips(vin);
