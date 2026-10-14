.headers on 
.mode column 

-- ---------------------------------------------------------
-- Insight idea 1: Does traffic slow the taxis down at rush hour?
-- ---------------------------------------------------------

SELECT pickup_hour,
       COUNT(*)                     AS trips,
       ROUND(AVG(avg_speed_mph), 1) AS avg_speed_mph,
       ROUND(AVG(total_amount), 2)  AS avg_total_fare
FROM trips
GROUP BY pickup_hour
ORDER BY pickup_hour;


-- ------------------------------------------------------------
-- Insight idea 2: Are airport trips a different kind of trip?
-- ------------------------------------------------------------

SELECT CASE is_airport_trip WHEN 1 THEN 'Airport trip' END AS trip_kind,
       COUNT(*)                                                    AS trips,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM trips), 1)   AS pct_of_trips,
       ROUND(AVG(trip_distance), 1)                                AS avg_miles,
       ROUND(AVG(trip_amount), 2)                                  AS avg_total_fare,   
       ROUND(100.0 * SUM(total_amount)) / (SELECT SUM(total_amount) FROM trips), 1 AS pct_of_revenue
FROM trips           
GROUP BY is_airport_trip;


-- -------------------------------------------------------------------
-- where do the busiest routes go?
-- -------------------------------------------------------------------

SELECT pz.zone_name AS pickup_zone,
       dz.zone_name AS dropoff_zone,
       COUNT(*)     AS trips,
       ROUND(AVG(t.total_amount), 2) AS avg_total_fare
FROM trips t  
JOIN zones pz ON pz.location_id = t.up_location_id
JOIN zones dz ON dz.location_id = t.do_location_id
GROUP BY t.pu_location_id, t.do_location_id
ORDER by trips DESC
LIMIT 10

-- Tips by borough, for card payments only

SELECT b.borough_name,
    COUNT(*)                 AS card_trips,
    ROUND(AVG(t.tip_pct), 1) AS avg_tip_pct
FROM trips t
JOIN zones z    ON z.location_id = t.pu_location_id
JOIN boroughs b ON b.borough_id = z.borough_id
WHERE t.tip_pct IS NOT NULL
GROUP BY b.borough_name
ORDER BY avg_tip_pct DESC;


-- Weekday vs weekend: when do people ride?
SELECT is_weekend,
       pickup_hour,
       COUNT(*) AS trips
FROM trips  
GROUP BY is_weekend, pickup_hour
ORDER BY is_weekend, pickup_hour;


-- How many trips cross a borough line?

SELECT ROUND(100.0 * AVG(is_cross_borough), 1) AS pct_cross_borough FROM trips;

-- What the cleaning step removed (the transparency log,summarised)
SELECT reason, record_count, percent_of_raw
FROM exclusion_summary
ORDER BY ecord _count DESC;