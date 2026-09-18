"""
PlumeBacktrace AI - Atmospheric Dispersion Physics & Inverse Vector Engine
Implements Inverse Gaussian Plume Modeling under Pasquill-Gifford atmospheric stability classes.
"""

import math
from typing import List, Dict, Any, Tuple

# Earth radius in meters for equirectangular local projection
R_EARTH = 6371000.0

def latlon_to_xy(lat: float, lon: float, lat0: float, lon0: float) -> Tuple[float, float]:
    """Convert lat/lon to local Cartesian meters relative to origin (lat0, lon0)."""
    x = math.radians(lon - lon0) * R_EARTH * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * R_EARTH
    return x, y

def xy_to_latlon(x: float, y: float, lat0: float, lon0: float) -> Tuple[float, float]:
    """Convert local Cartesian meters back to lat/lon relative to origin (lat0, lon0)."""
    lat = lat0 + math.degrees(y / R_EARTH)
    lon = lon0 + math.degrees(x / (R_EARTH * math.cos(math.radians(lat0))))
    return round(lat, 6), round(lon, 6)

def get_dispersion_sigma_y(distance_m: float, stability_class: str = "F") -> float:
    """
    Calculate crosswind dispersion coefficient sigma_y (in meters)
    using Pasquill-Gifford formulations.
    Default: Class F (Nighttime, stable nocturnal boundary layer, thermal inversion).
    """
    d = max(distance_m, 10.0)
    # Empirical power law parameters for Pasquill classes (distance in meters)
    params = {
        "D": (0.08, 0.90),   # Neutral
        "E": (0.06, 0.90),   # Slightly stable (dusk/early night)
        "F": (0.055, 0.903), # Stable night (classic off-peak release conditions)
    }
    a, b = params.get(stability_class.upper(), params["F"])
    return a * (d ** b)

def calculate_inverse_trajectory(
    plume_lat: float,
    plume_lon: float,
    wind_speed_mps: float,
    wind_direction_deg: float,
    max_distance_m: float = 6000.0,
    step_m: float = 100.0,
    stability_class: str = "F"
) -> Dict[str, Any]:
    """
    Back-calculate the upwind trajectory spine and 95% dispersion probability envelope.
    
    Meteorological wind direction (wind_direction_deg):
    Direction the wind blows FROM (0=N, 90=E, 180=S, 270=W).
    To trace backwards from the detected plume to the source, we follow the direction
    the wind came from!
    """
    # Ensure step_m and stability_class handling if passed positionally
    if isinstance(step_m, str):
        stability_class = step_m
        step_m = 100.0
    else:
        step_m = float(step_m)

    # Angle in Cartesian coordinate system (0 along +X East, 90 along +Y North)
    # Wind FROM theta means vector towards (theta + 180).
    # Backtrace vector (towards source) is therefore towards theta!
    cartesian_angle_rad = math.radians(90.0 - wind_direction_deg)
    ux = math.cos(cartesian_angle_rad) # East component
    uy = math.sin(cartesian_angle_rad) # North component

    # Perpendicular unit vector for crosswind width: (-uy, ux)
    px = -uy
    py = ux

    center_line_coords = []
    left_boundary = []
    right_boundary = []
    heatmap_points = []

    current_dist = 0.0
    while current_dist <= max_distance_m:
        # Cartesian position of center spine
        cx = current_dist * ux
        cy = current_dist * uy
        clat, clon = xy_to_latlon(cx, cy, plume_lat, plume_lon)
        center_line_coords.append([clon, clat])

        # Crosswind spread at this distance (2 * sigma_y covers ~95% of Gaussian plume)
        sigma_y = get_dispersion_sigma_y(current_dist, stability_class)
        half_width = 2.15 * sigma_y

        # Left and right bounds
        lx = cx + half_width * px
        ly = cy + half_width * py
        llat, llon = xy_to_latlon(lx, ly, plume_lat, plume_lon)
        left_boundary.append([llon, llat])

        rx = cx - half_width * px
        ry = cy - half_width * py
        rlat, rlon = xy_to_latlon(rx, ry, plume_lat, plume_lon)
        right_boundary.append([rlon, rlat])

        # Generate sample probability grid points for visual heatmap
        transport_time_min = round(current_dist / (max(wind_speed_mps, 0.5) * 60.0), 1)
        heatmap_points.append({
            "coordinates": [clon, clat],
            "distance_m": round(current_dist, 1),
            "transport_time_min": transport_time_min,
            "sigma_y_m": round(sigma_y, 1),
            "relative_intensity": max(0.05, round(1.0 - (current_dist / max_distance_m) * 0.7, 2))
        })

        current_dist += step_m

    # Assemble dispersion cone polygon: Plume origin -> Left envelope -> Right envelope reversed -> Origin
    cone_polygon = [center_line_coords[0]] + left_boundary + list(reversed(right_boundary)) + [center_line_coords[0]]

    return {
        "spine_geojson": {
            "type": "Feature",
            "properties": {
                "type": "central_backtrace_vector",
                "wind_direction_deg": wind_direction_deg,
                "wind_speed_mps": wind_speed_mps,
                "max_distance_m": max_distance_m
            },
            "geometry": {
                "type": "LineString",
                "coordinates": center_line_coords
            }
        },
        "cone_geojson": {
            "type": "Feature",
            "properties": {
                "type": "dispersion_envelope_95pct",
                "stability_class": stability_class
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [cone_polygon]
            }
        },
        "heatmap_points": heatmap_points,
        "wind_vector": {
            "ux": round(ux, 4),
            "uy": round(uy, 4),
            "speed_mps": wind_speed_mps,
            "direction_deg": wind_direction_deg
        }
    }
