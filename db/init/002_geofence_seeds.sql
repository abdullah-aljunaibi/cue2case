-- Long Beach / San Pedro Bay geofence seeds
-- These define operational zones for context-aware anomaly detection

-- Main approach channel (inbound lane, roughly NW heading)
INSERT INTO geofence (name, zone_type, geom) VALUES (
    'Long Beach Main Channel Approach',
    'approach',
    ST_GeomFromText('POLYGON((-118.22 33.70, -118.19 33.70, -118.16 33.73, -118.19 33.73, -118.22 33.70))', 4326)
);

-- Queens Gate entrance
INSERT INTO geofence (name, zone_type, geom) VALUES (
    'Queens Gate Entrance',
    'approach',
    ST_GeomFromText('POLYGON((-118.195 33.715, -118.185 33.715, -118.185 33.725, -118.195 33.725, -118.195 33.715))', 4326)
);

-- Outer anchorage area (vessels waiting for berth)
INSERT INTO geofence (name, zone_type, geom) VALUES (
    'Long Beach Outer Anchorage',
    'anchorage',
    ST_GeomFromText('POLYGON((-118.25 33.65, -118.15 33.65, -118.15 33.70, -118.25 33.70, -118.25 33.65))', 4326)
);

-- Inner harbor / terminal area
INSERT INTO geofence (name, zone_type, geom) VALUES (
    'Long Beach Inner Harbor',
    'harbor',
    ST_GeomFromText('POLYGON((-118.24 33.74, -118.18 33.74, -118.18 33.78, -118.24 33.78, -118.24 33.74))', 4326)
);

-- Port of Los Angeles terminal area
INSERT INTO geofence (name, zone_type, geom) VALUES (
    'Port of LA Terminal Area',
    'harbor',
    ST_GeomFromText('POLYGON((-118.29 33.72, -118.24 33.72, -118.24 33.76, -118.29 33.76, -118.29 33.72))', 4326)
);

-- Restricted zone near Naval Weapons Station Seal Beach
INSERT INTO geofence (name, zone_type, geom) VALUES (
    'Naval Weapons Station Seal Beach',
    'restricted',
    ST_GeomFromText('POLYGON((-118.10 33.72, -118.06 33.72, -118.06 33.76, -118.10 33.76, -118.10 33.72))', 4326)
);

-- Pilot station area
INSERT INTO geofence (name, zone_type, geom) VALUES (
    'LA/LB Pilot Station',
    'restricted',
    ST_GeomFromText('POLYGON((-118.21 33.70, -118.19 33.70, -118.19 33.72, -118.21 33.72, -118.21 33.70))', 4326)
);
