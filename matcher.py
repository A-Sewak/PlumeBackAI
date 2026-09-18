"""
PlumeBacktrace AI - Factory Raycasting & Culprit Scoring Engine
Computes spatial intersection, transport timing, chemical profile matching,
and statutory penalty estimates.
"""

import os
import json
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any
from engine import latlon_to_xy, get_dispersion_sigma_y

def load_factories_geojson(filepath: str) -> List[Dict[str, Any]]:
    """Load factories from GeoJSON file."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("features", [])

def match_suspect_factories(
    plume_lat: float,
    plume_lon: float,
    gas_type: str,
    gas_density_umol: float,
    wind_speed_mps: float,
    wind_direction_deg: float,
    detection_timestamp_iso: str,
    factories: List[Dict[str, Any]],
    stability_class: str = "F"
) -> List[Dict[str, Any]]:
    """
    Score all factories against the reverse dispersion plume.
    """
    # Backtrace heading vector (Cartesian)
    cartesian_angle_rad = math.radians(90.0 - wind_direction_deg)
    ux = math.cos(cartesian_angle_rad)
    uy = math.sin(cartesian_angle_rad)

    # Perpendicular unit vector: (-uy, ux)
    px = -uy
    py = ux

    try:
        dt_detect = datetime.fromisoformat(detection_timestamp_iso.replace("Z", "+00:00"))
    except Exception:
        dt_detect = datetime.utcnow()

    suspects = []

    for feature in factories:
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        coords = geom.get("coordinates", [])

        # Support Point or Polygon geometry (centroid)
        if geom.get("type") == "Point":
            flon, flat = coords[0], coords[1]
        elif geom.get("type") == "Polygon":
            poly_coords = coords[0]
            flon = sum(c[0] for c in poly_coords) / len(poly_coords)
            flat = sum(c[1] for c in poly_coords) / len(poly_coords)
        else:
            continue

        # Convert factory lat/lon to Cartesian meters relative to plume spike origin
        fx, fy = latlon_to_xy(flat, flon, plume_lat, plume_lon)
        dist_m = math.hypot(fx, fy)

        # Longitudinal distance along upwind vector
        d_upwind = fx * ux + fy * uy

        # Perpendicular crosswind distance from center line
        d_cross = abs(fx * px + fy * py)

        # Calculate dispersion width sigma_y with building downwash floor
        sigma_y = max(get_dispersion_sigma_y(max(d_upwind, 10.0), stability_class), 75.0)

        # 1. Spatial Probability with point-source stack and corridor tolerance
        if dist_m <= 350.0:
            # Direct stack or facility boundary detection
            p_spatial = 0.95 - (dist_m / 350.0) * 0.08
        elif d_upwind >= -150.0 and d_cross <= 4.0 * sigma_y:
            # Within reverse Gaussian dispersion corridor
            p_spatial = math.exp(-0.5 * ((d_cross / sigma_y) ** 2))
        elif dist_m <= 4000.0:
            # Nearby monitored industrial stack in regional corridor
            p_spatial = max(0.12, math.exp(-0.5 * (dist_m / 1600.0) ** 2) * 0.65)
        elif dist_m <= 8000.0:
            # Broader monitored industrial basin
            p_spatial = max(0.04, math.exp(-dist_m / 3500.0) * 0.35)
        else:
            continue

        # 2. Distance decay (closer sources to strong plumes have higher plausibility)
        p_distance = max(0.45, 1.0 - (dist_m / 10000.0))

        # 3. Chemical Profile Alignment
        known_emissions = [e.upper() for e in props.get("emissions", [])]
        gas_upper = gas_type.upper()
        if gas_upper in known_emissions or any(gas_upper in e for e in known_emissions):
            w_gas = 1.25
        elif props.get("category", "").lower() in ["tannery", "chemical", "dyeing"]:
            w_gas = 1.10
        else:
            w_gas = 0.70

        # 4. Compliance History Weight
        prior_violations = props.get("prior_violations_count", 0)
        w_history = 1.0 + min(0.20, prior_violations * 0.05)

        # Composite Confidence Score (0 - 100%)
        raw_score = p_spatial * p_distance * w_gas * w_history * 100.0
        confidence_score = min(99.4, max(15.0, round(raw_score, 1)))

        # Estimated release timing
        effective_dist = max(dist_m if dist_m < 350.0 else max(d_upwind, 50.0), 10.0)
        transport_time_sec = effective_dist / max(wind_speed_mps, 0.5)
        release_dt = dt_detect - timedelta(seconds=transport_time_sec)
        est_release_str = release_dt.strftime("%I:%M:%S %p IST")

        # Fine assessment under Indian Air Act (Section 21) based on pollutant concentration
        so2_approx_ugm3 = (gas_density_umol / 4.5) if gas_type == "SO2" else (gas_density_umol / 2.0)
        so2_factor = max(1.0, 1.0 + ((so2_approx_ugm3 - 20.0) / 20.0) * 1.35) if so2_approx_ugm3 > 20.0 else 1.0
        night_multiplier = 1.5 if (dt_detect.hour < 6 or dt_detect.hour >= 22) else 1.0
        calculated_fine_inr = int(min(10000000, max(250000, round((500000 * so2_factor * night_multiplier + (prior_violations * 200000)) / 10000) * 10000)))

        suspects.append({
            "factory_id": props.get("id", f"FAC-{len(suspects)+1}"),
            "name": props.get("name", "Unknown Industrial Unit"),
            "category": props.get("category", "General Manufacturing"),
            "coordinates": [flon, flat],
            "geometry": geom,
            "confidence_score": confidence_score,
            "distance_meters": round(dist_m if dist_m < 350.0 else max(d_upwind, dist_m * 0.5), 1),
            "crosswind_offset_m": round(d_cross, 1),
            "dispersion_sigma_y_m": round(sigma_y, 1),
            "transport_time_minutes": round(transport_time_sec / 60.0, 1),
            "est_release_time": est_release_str,
            "registration_no": props.get("registration_no", "TNPCB/IND/2024/9912"),
            "address": props.get("address", "SIPCOT Industrial Complex, Ranipet, TN"),
            "primary_chemicals": props.get("emissions", ["SO2", "Effluents"]),
            "calculated_fine_inr": calculated_fine_inr,
            "prior_violations": prior_violations,
            "statutory_act": "Section 21, Air (Prevention and Control of Pollution) Act, 1981"
        })

    suspects.sort(key=lambda s: (s["confidence_score"], -s["distance_meters"]), reverse=True)

    # Tag primary culprit
    for idx, s in enumerate(suspects):
        s["rank"] = idx + 1
        s["status"] = "PRIMARY_CULPRIT" if idx == 0 and s["confidence_score"] >= 65.0 else ("SUSPECT" if s["confidence_score"] >= 40.0 else "LOW_PROBABILITY")

    return suspects
