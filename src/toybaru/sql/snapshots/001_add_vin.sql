-- Add vin column if missing
ALTER TABLE snapshots ADD COLUMN vin TEXT NOT NULL DEFAULT '';
