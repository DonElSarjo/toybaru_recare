-- name: upsert_check
SELECT 1 FROM trips WHERE id = ?;

-- name: latest_timestamp
SELECT MAX(start_ts) FROM trips;

-- name: trip_count
SELECT COUNT(*) FROM trips;

-- name: overview
SELECT
    COUNT(*) as total_trips,
    SUM(length_m) as total_distance_m,
    SUM(duration_s) as total_duration_s,
    AVG(avg_speed) as avg_speed,
    MAX(max_speed) as max_speed,
    AVG(score_global) as avg_score,
    MIN(start_ts) as first_trip,
    MAX(start_ts) as last_trip,
    SUM(hdc_charge_dist) as total_reku_m,
    SUM(hdc_ev_distance) as total_ev_m,
    SUM(hdc_eco_dist) as total_eco_m,
    SUM(hdc_power_dist) as total_power_m,
    SUM(duration_idle_s) as total_idle_s,
    SUM(length_highway) as total_highway_m,
    SUM(duration_highway) as total_highway_s,
    AVG(score_acceleration) as avg_score_accel,
    AVG(score_braking) as avg_score_braking,
    AVG(score_constant_speed) as avg_score_consistency,
    SUM(CASE WHEN night_trip=1 THEN 1 ELSE 0 END) as night_trips,
    SUM(length_overspeed) as total_overspeed_m
FROM trips {where};

-- name: monthly
SELECT
    SUBSTR(start_ts,1,7) as month,
    COUNT(*) as trips,
    ROUND(SUM(length_m)/1000.0) as km,
    ROUND(AVG(avg_speed),1) as spd,
    ROUND(AVG(score_global),1) as score,
    ROUND(AVG(CASE WHEN hdc_ev_distance>0 THEN hdc_charge_dist*100.0/hdc_ev_distance END),1) as reku,
    ROUND(AVG(CASE WHEN hdc_ev_distance>0 THEN hdc_eco_dist*100.0/hdc_ev_distance END),1) as eco,
    ROUND(AVG(CASE WHEN hdc_ev_distance>0 THEN hdc_power_dist*100.0/hdc_ev_distance END),1) as pwr
FROM trips {where}
GROUP BY month ORDER BY month;

-- name: weekday
SELECT
    CASE CAST(strftime('%w', start_ts) AS INTEGER)
        WHEN 0 THEN 'Sun' WHEN 1 THEN 'Mon' WHEN 2 THEN 'Tue' WHEN 3 THEN 'Wed'
        WHEN 4 THEN 'Thu' WHEN 5 THEN 'Fri' WHEN 6 THEN 'Sat' END as day,
    COUNT(*) as trips,
    ROUND(SUM(length_m)/1000.0) as km
FROM trips {where}
GROUP BY strftime('%w', start_ts)
ORDER BY CAST(strftime('%w', start_ts) AS INTEGER);

-- name: hourly
SELECT
    CAST(SUBSTR(start_ts,12,2) AS INTEGER) as hour,
    COUNT(*) as trips,
    ROUND(SUM(length_m)/1000.0) as km
FROM trips {where}
GROUP BY hour ORDER BY hour;

-- name: speed_categories
SELECT
    SUM(CASE WHEN avg_speed < 40 THEN 1 ELSE 0 END) as city,
    SUM(CASE WHEN avg_speed >= 40 AND avg_speed < 80 THEN 1 ELSE 0 END) as rural,
    SUM(CASE WHEN avg_speed >= 80 THEN 1 ELSE 0 END) as highway,
    SUM(CASE WHEN avg_speed < 40 THEN length_m ELSE 0 END) as city_m,
    SUM(CASE WHEN avg_speed >= 40 AND avg_speed < 80 THEN length_m ELSE 0 END) as rural_m,
    SUM(CASE WHEN avg_speed >= 80 THEN length_m ELSE 0 END) as highway_m
FROM trips {where};

-- name: score_distribution
SELECT
    (score_global / 10) * 10 as bucket,
    COUNT(*) as cnt
FROM trips {where} AND score_global IS NOT NULL
GROUP BY bucket ORDER BY bucket;

-- name: record_longest
SELECT id, length_m, start_ts FROM trips {where} ORDER BY length_m DESC LIMIT 1;

-- name: record_fastest_avg
SELECT id, avg_speed, start_ts FROM trips {where} ORDER BY avg_speed DESC LIMIT 1;

-- name: record_best_score
SELECT id, score_global, start_ts FROM trips {where} AND score_global IS NOT NULL ORDER BY score_global DESC LIMIT 1;

-- name: record_best_reku
SELECT id, ROUND(hdc_charge_dist*100.0/hdc_ev_distance,1), start_ts FROM trips {where} AND hdc_ev_distance>0 ORDER BY hdc_charge_dist*1.0/hdc_ev_distance DESC LIMIT 1;

-- name: record_top_speed
SELECT id, max_speed, start_ts FROM trips {where} ORDER BY max_speed DESC LIMIT 1;

-- name: best_day
SELECT
    SUBSTR(start_ts,1,10) as day,
    ROUND(SUM(length_m)/1000.0,1) as km,
    COUNT(*) as trips
FROM trips {where}
GROUP BY day ORDER BY km DESC LIMIT 1;

-- name: simple_stats
SELECT
    COUNT(*) as total_trips,
    SUM(length_m) as total_distance_m,
    SUM(duration_s) as total_duration_s,
    AVG(avg_speed) as avg_speed,
    MAX(max_speed) as max_speed,
    AVG(score_global) as avg_score,
    MIN(start_ts) as first_trip,
    MAX(start_ts) as last_trip,
    SUM(hdc_charge_dist) as total_reku_m,
    SUM(hdc_ev_distance) as total_ev_m,
    SUM(hdc_eco_dist) as total_eco_m,
    SUM(hdc_power_dist) as total_power_m
FROM trips;
