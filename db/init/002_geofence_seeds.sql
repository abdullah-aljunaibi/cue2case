-- Long Beach / San Pedro Bay geofence seeds
-- These define operational zones for context-aware anomaly detection

-- Main approach channel (inbound lane, roughly NW heading)
INSERT INTO geofence (name, zone_type, geom)
SELECT
    'Long Beach Main Channel Approach',
    'approach',
    ST_GeomFromText('POLYGON((-118.22 33.70, -118.19 33.70, -118.16 33.73, -118.19 33.73, -118.22 33.70))', 4326)
WHERE NOT EXISTS (
    SELECT 1 FROM geofence WHERE name = 'Long Beach Main Channel Approach'
);

-- Queens Gate entrance
INSERT INTO geofence (name, zone_type, geom)
SELECT
    'Queens Gate Entrance',
    'approach',
    ST_GeomFromText('POLYGON((-118.195 33.715, -118.185 33.715, -118.185 33.725, -118.195 33.725, -118.195 33.715))', 4326)
WHERE NOT EXISTS (
    SELECT 1 FROM geofence WHERE name = 'Queens Gate Entrance'
);

-- Outer anchorage area (vessels waiting for berth)
INSERT INTO geofence (name, zone_type, geom)
SELECT
    'Long Beach Outer Anchorage',
    'anchorage',
    ST_GeomFromText('POLYGON((-118.25 33.65, -118.15 33.65, -118.15 33.70, -118.25 33.70, -118.25 33.65))', 4326)
WHERE NOT EXISTS (
    SELECT 1 FROM geofence WHERE name = 'Long Beach Outer Anchorage'
);

-- Inner harbor / terminal area
INSERT INTO geofence (name, zone_type, geom)
SELECT
    'Long Beach Inner Harbor',
    'harbor',
    ST_GeomFromText('POLYGON((-118.24 33.74, -118.18 33.74, -118.18 33.78, -118.24 33.78, -118.24 33.74))', 4326)
WHERE NOT EXISTS (
    SELECT 1 FROM geofence WHERE name = 'Long Beach Inner Harbor'
);

-- Port of Los Angeles terminal area
INSERT INTO geofence (name, zone_type, geom)
SELECT
    'Port of LA Terminal Area',
    'harbor',
    ST_GeomFromText('POLYGON((-118.29 33.72, -118.24 33.72, -118.24 33.76, -118.29 33.76, -118.29 33.72))', 4326)
WHERE NOT EXISTS (
    SELECT 1 FROM geofence WHERE name = 'Port of LA Terminal Area'
);

-- Restricted zone near Naval Weapons Station Seal Beach
INSERT INTO geofence (name, zone_type, geom)
SELECT
    'Naval Weapons Station Seal Beach',
    'restricted',
    ST_GeomFromText('POLYGON((-118.10 33.72, -118.06 33.72, -118.06 33.76, -118.10 33.76, -118.10 33.72))', 4326)
WHERE NOT EXISTS (
    SELECT 1 FROM geofence WHERE name = 'Naval Weapons Station Seal Beach'
);

-- Pilot station area
INSERT INTO geofence (name, zone_type, geom)
SELECT
    'LA/LB Pilot Station',
    'restricted',
    ST_GeomFromText('POLYGON((-118.21 33.70, -118.19 33.70, -118.19 33.72, -118.21 33.72, -118.21 33.70))', 4326)
WHERE NOT EXISTS (
    SELECT 1 FROM geofence WHERE name = 'LA/LB Pilot Station'
);
