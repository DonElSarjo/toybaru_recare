-- name: upsert_check
SELECT 1 FROM charge_sessions WHERE vin = ? AND start_time = ?;

-- name: latest_timestamp
SELECT MAX(start_time) FROM charge_sessions;

-- name: charge_count
SELECT COUNT(*) FROM charge_sessions;
