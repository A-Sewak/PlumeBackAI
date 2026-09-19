"""
PlumeBacktrace AI - High Performance FastAPI Backend
Serves atmospheric inverse dispersion calculations, spatial factory matching,
and statutory legal notice generation.
"""

import os
import json
import math
import io
import csv
import urllib.request
import secrets
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
import auth
from auth import get_current_user, require_roles, sanitize_user, log_audit_action, load_system_state, save_system_state
from engine import calculate_inverse_trajectory
from matcher import load_factories_geojson, match_suspect_factories
from notice_generator import generate_violation_notice_pdf, generate_curfew_violations_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
FACTORIES_PATH = os.path.join(DATA_DIR, "factories.geojson")
SPIKES_PATH = os.path.join(DATA_DIR, "satellite_spikes.json")
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Initialize SQLite database on startup
db.init_db()

def add_verified_factory_to_geojson(user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Adds a newly verified industry to factories.geojson and returns the GeoJSON feature."""
    # ponytail: append Point feature to GeoJSON file, stdlib json/os only
    if not os.path.exists(FACTORIES_PATH):
        return None
    try:
        with open(FACTORIES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"type": "FeatureCollection", "features": []}

    features = data.get("features", [])
    fac_name = user.get("factory_name") or user.get("name")

    for f in features:
        if f.get("properties", {}).get("name", "").strip().lower() == fac_name.strip().lower():
            return f

    new_id = f"FAC-{len(features) + 1:02d}"
    lat = float(user.get("industry_lat") or 12.9250)
    lon = float(user.get("industry_lon") or 79.3300)
    reg_code = secrets.token_hex(2).upper()

    new_feature = {
        "type": "Feature",
        "properties": {
            "id": new_id,
            "name": fac_name,
            "category": user.get("industry_type") or "Industrial Manufacturing",
            "registration_no": f"TNPCB/RN/NEW-{reg_code}",
            "address": user.get("industry_address") or "Ranipet Industrial Zone",
            "emissions": ["SO2", "NO2", "PM2.5"],
            "prior_violations_count": 0,
            "stack_height_m": 25.0,
            "night_shift_active": True
        },
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat]
        }
    }

    features.append(new_feature)
    data["features"] = features

    with open(FACTORIES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return new_feature

# Auto-load .env file if it exists
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

app = FastAPI(
    title="PlumeBacktrace AI - Backend Engine",
    description="Atmospheric Satellite Gas Plume Inversion & Culprit Pinpointing API",
    version="1.0.0"
)

# Enable CORS for external frontends (React, Vite, Next.js)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder for built-in dashboard
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Request / Response Schemas
class TraceRequest(BaseModel):
    plume_lat: float = Field(..., description="Latitude of detected satellite gas plume spike")
    plume_lon: float = Field(..., description="Longitude of detected satellite gas plume spike")
    gas_type: str = Field("SO2", description="Gas species (SO2, NO2, NH3, etc.)")
    gas_density_umol: float = Field(450.0, description="Concentration in micromoles per m2")
    wind_speed_mps: float = Field(4.2, ge=0.1, le=40.0, description="Wind speed in meters per second")
    wind_direction_deg: float = Field(240.0, ge=0.0, le=360.0, description="Meteorological wind direction (from 0-360 deg)")
    timestamp: str = Field("2026-09-18T02:30:00Z", description="ISO timestamp of satellite sounder pass")
    stability_class: str = Field("F", description="Pasquill stability class (D, E, F)")
    max_distance_m: float = Field(6000.0, description="Max inverse backtrace search distance")

class NoticeRequest(BaseModel):
    culprit: Dict[str, Any]
    plume_info: Dict[str, Any]

@app.get("/", response_class=HTMLResponse)
@app.get("/health-dashboard", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the built-in dark-mode 3D tactical and environmental health dashboard."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>PlumeBacktrace AI API is running. Access /docs for OpenAPI specs.</h1>"

class ConfigUpdate(BaseModel):
    google_maps_api_key: Optional[str] = None
    openweather_api_key: Optional[str] = None

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "engine": "Inverse Gaussian Plume Dispersion Model v1.0",
        "has_google_maps_key": bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
        "has_openweather_key": bool(os.environ.get("OPENWEATHER_API_KEY"))
    }

@app.get("/api/config")
def get_config():
    """Return public configuration including Google Maps & OpenWeather API status."""
    g_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    w_key = os.environ.get("OPENWEATHER_API_KEY", "")
    return {
        "google_maps_api_key": g_key,
        "has_google_maps_key": bool(g_key),
        "openweather_api_key": w_key,
        "has_openweather_key": bool(w_key)
    }

@app.post("/api/config")
def update_config(cfg: ConfigUpdate):
    """Save Google Maps and OpenWeather API keys to environment and persist to .env."""
    env_lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            env_lines = f.readlines()

    keys_to_update = {}
    if cfg.google_maps_api_key is not None:
        k = cfg.google_maps_api_key.strip()
        os.environ["GOOGLE_MAPS_API_KEY"] = k
        keys_to_update["GOOGLE_MAPS_API_KEY"] = k
        
    if cfg.openweather_api_key is not None:
        k = cfg.openweather_api_key.strip()
        os.environ["OPENWEATHER_API_KEY"] = k
        keys_to_update["OPENWEATHER_API_KEY"] = k

    new_lines = []
    handled_keys = set()
    for line in env_lines:
        replaced = False
        for env_k, env_v in keys_to_update.items():
            if line.startswith(f"{env_k}="):
                new_lines.append(f"{env_k}={env_v}\n")
                handled_keys.add(env_k)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    for env_k, env_v in keys_to_update.items():
        if env_k not in handled_keys:
            new_lines.append(f"{env_k}={env_v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    g_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    w_key = os.environ.get("OPENWEATHER_API_KEY", "")
    return {
        "status": "success",
        "google_maps_api_key": g_key,
        "has_google_maps_key": bool(g_key),
        "openweather_api_key": w_key,
        "has_openweather_key": bool(w_key)
    }

@app.get("/api/factories")
def get_factories():
    """Return all factories registered in the current active locality."""
    factories = load_factories_geojson(FACTORIES_PATH)
    return {
        "type": "FeatureCollection",
        "count": len(factories),
        "features": factories
    }

@app.get("/api/spikes")
def get_spikes():
    """Return sample Sentinel-5P satellite anomaly presets."""
    if os.path.exists(SPIKES_PATH):
        with open(SPIKES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

@app.post("/api/trace")
def run_backtrace(req: TraceRequest):
    """
    Core AI & Physics Engine:
    1. Traces the atmospheric inverse dispersion cone backward from the plume.
    2. Raycasts against all factory footprints.
    3. Returns ranked suspects, probability scores, and map GeoJSON layers.
    """
    # 1. Physics Trajectory Calculation
    trajectory = calculate_inverse_trajectory(
        plume_lat=req.plume_lat,
        plume_lon=req.plume_lon,
        wind_speed_mps=req.wind_speed_mps,
        wind_direction_deg=req.wind_direction_deg,
        max_distance_m=req.max_distance_m,
        stability_class=req.stability_class
    )

    # 2. Factory Raycast Matching & Scoring
    factories = load_factories_geojson(FACTORIES_PATH)
    suspects = match_suspect_factories(
        plume_lat=req.plume_lat,
        plume_lon=req.plume_lon,
        gas_type=req.gas_type,
        gas_density_umol=req.gas_density_umol,
        wind_speed_mps=req.wind_speed_mps,
        wind_direction_deg=req.wind_direction_deg,
        detection_timestamp_iso=req.timestamp,
        factories=factories,
        stability_class=req.stability_class
    )

    primary_culprit = suspects[0] if suspects else None

    # Auto-record in SQLite if detected during 10 PM - 6 AM curfew window
    if primary_culprit and db.is_curfew_hours(req.timestamp):
        db.record_night_violation(
            factory=primary_culprit,
            pollutant=req.gas_type,
            concentration=req.gas_density_umol,
            plume_lat=req.plume_lat,
            plume_lon=req.plume_lon,
            detection_timestamp=req.timestamp,
            source="scenario_trace"
        )

    return {
        "status": "success",
        "timestamp": req.timestamp,
        "wind_vector": trajectory["wind_vector"],
        "layers": {
            "spine": trajectory["spine_geojson"],
            "cone": trajectory["cone_geojson"],
            "heatmap_points": trajectory["heatmap_points"]
        },
        "suspects_count": len(suspects),
        "primary_culprit": primary_culprit,
        "suspects": suspects
    }

@app.post("/api/notice/pdf")
def download_notice_pdf(req: NoticeRequest):
    """Generate and return official Section 21 statutory violation notice PDF."""
    pdf_bytes = generate_violation_notice_pdf(
        culprit=req.culprit,
        plume_info=req.plume_info
    )
    filename = f"Statutory_Notice_{req.culprit.get('factory_id', 'VIOLATION')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

def get_realtime_pollution(lat: float, lon: float) -> Dict[str, Any]:
    """Fetch real-time air pollution data from OpenWeather API with local physical model fallback."""
    key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
    if key:
        try:
            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={key}"
            req = urllib.request.Request(url, headers={"User-Agent": "PlumeBacktrace/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                item = data.get("list", [{}])[0]
                comp = item.get("components", {})
                ow_so2 = float(comp.get("so2", 0.0))
                # Superimpose industrial stack point-source emissions on OpenWeather ambient baseline
                stack_so2 = 0.0
                factories = load_factories_geojson(FACTORIES_PATH)
                for f in factories:
                    fc = f.get("geometry", {}).get("coordinates", [])
                    if f.get("geometry", {}).get("type") == "Polygon" and fc:
                        flat, flon = fc[0][0][1], fc[0][0][0]
                    elif f.get("geometry", {}).get("type") == "Point" and fc:
                        flat, flon = fc[1], fc[0]
                    else:
                        continue
                    d = math.hypot((lat - flat) * 111000, (lon - flon) * 111000 * math.cos(math.radians(lat)))
                    if d < 3500:
                        stack_so2 = max(stack_so2, round(78.0 * (1.0 - (d / 4000.0)), 1))
                eff_so2 = round(ow_so2 + stack_so2, 2)
                return {
                    "source": "OpenWeather Air Pollution API (Live Station)",
                    "so2": eff_so2,
                    "no2": float(comp.get("no2", 0.0)),
                    "co": float(comp.get("co", 0.0)),
                    "aqi": 4 if eff_so2 >= 80 else (3 if eff_so2 >= 40 else (2 if eff_so2 >= 20 else item.get("main", {}).get("aqi", 2))),
                    "components": comp
                }
        except Exception:
            pass

    # Physical atmospheric gradient fallback: proximity to monitored industrial stacks
    factories = load_factories_geojson(FACTORIES_PATH)
    min_dist_m = 99999.0
    for f in factories:
        fc = f.get("geometry", {}).get("coordinates", [])
        if f.get("geometry", {}).get("type") == "Polygon" and fc:
            flat, flon = fc[0][0][1], fc[0][0][0]
        elif f.get("geometry", {}).get("type") == "Point" and fc:
            flat, flon = fc[1], fc[0]
        else:
            continue
        d = math.hypot((lat - flat) * 111000, (lon - flon) * 111000 * math.cos(math.radians(lat)))
        if d < min_dist_m:
            min_dist_m = d

    # Elevated if within 4km of industrial tannery/chemical stacks
    if min_dist_m < 4000:
        base_so2 = max(24.0, round(92.0 * (1.0 - (min_dist_m / 4500.0)), 1))
    else:
        base_so2 = round(max(6.0, 16.0 - (min_dist_m / 6000.0)), 1)

    return {
        "source": "Physical Atmospheric Gradient Model (Configure OpenWeather Key for live station)",
        "so2": base_so2,
        "no2": round(base_so2 * 0.42, 1),
        "co": round(base_so2 * 2.8, 1),
        "aqi": 3 if base_so2 > 40 else 2,
        "components": {
            "so2": base_so2,
            "no2": round(base_so2 * 0.42, 1),
            "pm2_5": round(base_so2 * 0.65, 1)
        }
    }

def generate_circle_geojson(center_lat: float, center_lon: float, radius_km: float, num_pts: int = 36) -> Dict[str, Any]:
    """Generate GeoJSON circle polygon for map rendering."""
    radius_m = radius_km * 1000.0
    coords = []
    for i in range(num_pts + 1):
        angle = 2.0 * math.pi * (i % num_pts) / num_pts
        dy = radius_m * math.cos(angle)
        dx = radius_m * math.sin(angle)
        pt_lat = center_lat + math.degrees(dy / 6371000.0)
        pt_lon = center_lon + math.degrees(dx / (6371000.0 * math.cos(math.radians(center_lat))))
        coords.append([round(pt_lon, 6), round(pt_lat, 6)])
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords]
        },
        "properties": {
            "center": [center_lon, center_lat],
            "radius_km": radius_km
        }
    }


def calculate_openweather_fine(
    so2_ugm3: float,
    aqi: int = 2,
    is_curfew: bool = False,
    prior_violations: int = 0
) -> Dict[str, Any]:
    """
    Generate approximate statutory environmental compensation fine based on OpenWeather API location pollution data.
    CPCB / Air Act Section 21 statutory formula:
    EC = Base_Fine * (1 + Excess_SO2_Ratio) * AQI_Severity_Multiplier * Curfew_Multiplier + Recidivism
    """
    cpcb_baseline_ugm3 = 20.0  # WHO / CPCB Safe Ambient Guideline
    base_fine_inr = 500000     # Rs. 5 Lakhs Statutory Baseline
    
    if so2_ugm3 > cpcb_baseline_ugm3:
        so2_excess_ratio = (so2_ugm3 - cpcb_baseline_ugm3) / cpcb_baseline_ugm3
        so2_factor = 1.0 + so2_excess_ratio * 1.35
    else:
        so2_excess_ratio = 0.0
        so2_factor = max(0.5, so2_ugm3 / cpcb_baseline_ugm3)
        
    aqi_multipliers = {1: 1.0, 2: 1.15, 3: 1.45, 4: 1.85, 5: 2.5}
    aqi_mult = aqi_multipliers.get(int(aqi), 1.2)
    curfew_mult = 1.5 if is_curfew else 1.0
    history_penalty = prior_violations * 200000
    
    raw_fine = (base_fine_inr * so2_factor * aqi_mult * curfew_mult) + history_penalty
    total_fine = int(min(10000000, max(150000, round(raw_fine / 10000.0) * 10000)))
    
    return {
        "total_fine_inr": total_fine,
        "base_fine_inr": base_fine_inr,
        "so2_ugm3": round(so2_ugm3, 1),
        "cpcb_baseline_ugm3": cpcb_baseline_ugm3,
        "so2_excess_ratio": round(so2_excess_ratio, 2),
        "aqi": int(aqi),
        "aqi_multiplier": aqi_mult,
        "is_curfew": is_curfew,
        "curfew_multiplier": curfew_mult,
        "history_penalty_inr": history_penalty,
        "statutory_act": "Section 21, Air (Prevention and Control of Pollution) Act, 1981"
    }

@app.get("/api/realtime-emission")
def get_realtime_emission(
    lat: float,
    lon: float,
    wind_speed_mps: float = 4.0,
    wind_direction_deg: float = 224.0,
    factory_name: Optional[str] = None
):
    """
    Fetch live OpenWeather SO2 emission data for a clicked coordinate on the map.
    Constructs a live Satellite Detection Event scenario with emission pinpoint data,
    approximate statutory fine, and prepares parameters for immediate inverse dispersion test.
    """
    pollution = get_realtime_pollution(lat, lon)
    so2_ugm3 = float(pollution.get("so2", 0.0))
    gas_density_umol = round(max(30.0, so2_ugm3 * 4.5), 1)
    aqi = int(pollution.get("aqi", 2))
    is_curfew = db.is_curfew_hours()
    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    fine_assessment = calculate_openweather_fine(
        so2_ugm3=so2_ugm3,
        aqi=aqi,
        is_curfew=is_curfew
    )

    title = f"Live SO2 at {factory_name}" if factory_name else f"Live SO2 Emission ({round(lat, 4)}°N, {round(lon, 4)}°E)"
    locality = factory_name if factory_name else "Monitored Industrial Corridor"

    scenario = {
        "id": f"LIVE-SO2-{abs(hash((round(lat, 4), round(lon, 4)))) % 10000:04d}",
        "title": title,
        "description": f"Real-time SO2 emission detected via OpenWeather sounder ({so2_ugm3} µg/m³ / {gas_density_umol} µmol/m²).",
        "locality": locality,
        "target_factory": factory_name,
        "plume_lat": round(lat, 6),
        "plume_lon": round(lon, 6),
        "gas_type": "SO2",
        "so2_ugm3": so2_ugm3,
        "gas_density_umol": gas_density_umol,
        "wind_speed_mps": wind_speed_mps,
        "wind_direction_deg": wind_direction_deg,
        "timestamp": now_iso,
        "is_live": True,
        "expected_culprit": factory_name if factory_name else "To be pinpointed via Inverse Dispersion AI"
    }

    return {
        "status": "success",
        "scenario": scenario,
        "lat": lat,
        "lon": lon,
        "factory_name": factory_name,
        "so2_ugm3": so2_ugm3,
        "gas_density_umol": gas_density_umol,
        "source": pollution.get("source"),
        "aqi": aqi,
        "fine_assessment": fine_assessment,
        "approximate_statutory_fine": fine_assessment["total_fine_inr"],
        "is_curfew": is_curfew
    }

@app.get("/api/so2-radius")
def search_so2_radius(
    lat: float,
    lon: float,
    radius_km: float = 3.0,
    wind_speed_mps: float = 4.0,
    wind_direction_deg: float = 195.0
):
    """
    Sample real-time SO2 concentration in a circular radius around a point or user location.
    Uses OpenWeather Air Pollution API with local atmospheric gradient fallback.
    Detects peak SO2, runs inverse backtrace, and auto-logs 10 PM - 6 AM curfew violations.
    """
    # ponytail: clamp radius between 200m and 25km to cleanly support 0-20km slider
    radius_m = max(200.0, min(25000.0, radius_km * 1000.0))
    radius_km_clamped = radius_m / 1000.0
    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    is_curfew = db.is_curfew_hours()

    samples = []
    # 1. Center sample
    center_data = get_realtime_pollution(lat, lon)
    samples.append({
        "label": "Center Point",
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "distance_m": 0,
        "so2_ugm3": center_data["so2"],
        "aqi": center_data["aqi"],
        "source": center_data["source"]
    })

    # 2. Radial perimeter samples (8 compass points)
    bearings = [
        (0, "North"), (45, "North-East"), (90, "East"), (135, "South-East"),
        (180, "South"), (225, "South-West"), (270, "West"), (315, "North-West")
    ]
    for deg, label in bearings:
        rad = math.radians(deg)
        dy = radius_m * math.cos(rad)
        dx = radius_m * math.sin(rad)
        pt_lat = lat + math.degrees(dy / 6371000.0)
        pt_lon = lon + math.degrees(dx / (6371000.0 * math.cos(math.radians(lat))))
        pt_data = get_realtime_pollution(pt_lat, pt_lon)
        samples.append({
            "label": f"{label} ({radius_km_clamped}km)",
            "lat": round(pt_lat, 5),
            "lon": round(pt_lon, 5),
            "distance_m": round(radius_m),
            "so2_ugm3": pt_data["so2"],
            "aqi": pt_data["aqi"],
            "source": pt_data["source"]
        })

    # 3. Check factories within this circular radius
    factories = load_factories_geojson(FACTORIES_PATH)
    factories_inside = []
    exceeding_industries = []
    for f in factories:
        geom = f.get("geometry", {})
        fc = geom.get("coordinates", [])
        if geom.get("type") == "Polygon" and fc:
            flat, flon = fc[0][0][1], fc[0][0][0]
        elif geom.get("type") == "Point" and fc:
            flat, flon = fc[1], fc[0]
        else:
            continue
        d = math.hypot((lat - flat) * 111000, (lon - flon) * 111000 * math.cos(math.radians(lat)))
        if d <= radius_m:
            factories_inside.append(f)
            fdata = get_realtime_pollution(flat, flon)
            props = f.get("properties", {})
            f_fine = calculate_openweather_fine(
                so2_ugm3=fdata["so2"],
                aqi=fdata.get("aqi", 2),
                is_curfew=is_curfew,
                prior_violations=props.get("prior_violations_count", 0)
            )
            # Threshold: >= 20.0 ug/m3 is the CPCB safe ambient limit
            is_exc = fdata["so2"] >= 20.0
            ind_record = {
                "id": props.get("id"),
                "factory_id": props.get("id"),
                "name": props.get("name", "Industry"),
                "registration_no": props.get("registration_no", "N/A"),
                "category": props.get("category", "General Industry"),
                "lat": round(flat, 5),
                "lon": round(flon, 5),
                "distance_m": round(d),
                "distance_km": round(d / 1000.0, 2),
                "so2_ugm3": fdata["so2"],
                "aqi": fdata["aqi"],
                "source": fdata["source"],
                "is_exceeding": is_exc,
                "fine_inr": f_fine["total_fine_inr"],
                "fine_assessment": f_fine
            }
            if is_exc:
                exceeding_industries.append(ind_record)

            samples.append({
                "label": props.get("name", "Industry"),
                "lat": round(flat, 5),
                "lon": round(flon, 5),
                "distance_m": round(d),
                "so2_ugm3": fdata["so2"],
                "aqi": fdata["aqi"],
                "source": fdata["source"]
            })

    peak_sample = max(samples, key=lambda s: s["so2_ugm3"])
    
    primary_culprit = None
    trajectory = None
    recorded_id = None

    if peak_sample["so2_ugm3"] >= 20.0:
        gas_density_umol = round(peak_sample["so2_ugm3"] * 4.5, 1)
        trajectory = calculate_inverse_trajectory(
            plume_lat=peak_sample["lat"],
            plume_lon=peak_sample["lon"],
            wind_speed_mps=wind_speed_mps,
            wind_direction_deg=wind_direction_deg,
            max_distance_m=radius_m * 1.5,
            stability_class="F"
        )
        suspects = match_suspect_factories(
            plume_lat=peak_sample["lat"],
            plume_lon=peak_sample["lon"],
            gas_type="SO2",
            gas_density_umol=gas_density_umol,
            wind_speed_mps=wind_speed_mps,
            wind_direction_deg=wind_direction_deg,
            detection_timestamp_iso=now_iso,
            factories=factories,
            stability_class="F"
        )
        if suspects:
            primary_culprit = suspects[0]

    # Calculate approximate statutory fine based on OpenWeather API location reading
    fine_assessment = calculate_openweather_fine(
        so2_ugm3=peak_sample["so2_ugm3"],
        aqi=peak_sample.get("aqi", 2),
        is_curfew=is_curfew,
        prior_violations=primary_culprit.get("prior_violations", 0) if primary_culprit else 0
    )

    if primary_culprit:
        primary_culprit["calculated_fine_inr"] = fine_assessment["total_fine_inr"]
        primary_culprit["fine_assessment"] = fine_assessment

    # ponytail: read-only radius scan calculates fine assessment without inserting duplicate violation records
    recorded_id = None

    circle_geojson = generate_circle_geojson(lat, lon, radius_km_clamped)

    return {
        "status": "success",
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km_clamped,
        "circle_geojson": circle_geojson,
        "samples_count": len(samples),
        "center_so2_ugm3": center_data["so2"],
        "peak_sample": peak_sample,
        "samples": samples,
        "exceeding_industries": exceeding_industries,
        "exceeding_count": len(exceeding_industries),
        "layers": {
            "spine": trajectory["spine_geojson"],
            "cone": trajectory["cone_geojson"],
            "heatmap_points": trajectory["heatmap_points"]
        } if trajectory else None,
        "trajectory": trajectory,
        "primary_culprit": primary_culprit,
        "fine_assessment": fine_assessment,
        "approximate_statutory_fine": fine_assessment["total_fine_inr"],
        "is_night_curfew": is_curfew,
        "recorded_violation_id": recorded_id,
        "message": f"Radius scan ({radius_km_clamped} km) detected peak SO2 of {peak_sample['so2_ugm3']} µg/m³ ({peak_sample['label']}). " + (
            f"Pinpointed {primary_culprit['name']} ({primary_culprit['confidence_score']}% match, Fine: ₹{fine_assessment['total_fine_inr']:,})!" if primary_culprit else f"Assessed approximate fine: ₹{fine_assessment['total_fine_inr']:,}."
        ) + (" [RECORDED TO 10 PM - 6 AM CURFEW DATABASE]" if recorded_id else "")
    }

@app.get("/api/night-violations")
def get_night_violations():
    """Return all recorded 10 PM - 6 AM night curfew violations."""
    rows = db.get_all_night_violations()
    return {
        "status": "success",
        "monitoring_scope": "24/7 Continuous Statutory Exceedance Enforcement",
        "total_violations": len(rows),
        "total_penalties_inr": sum(r["penalty_inr"] for r in rows),
        "violations": rows
    }

@app.get("/api/night-violations/export")
def export_night_violations_csv():
    """Export all compiled continuous violations as a downloadable CSV report."""
    rows = db.get_all_night_violations()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Record ID", "Factory ID", "Company Name", "Registration No",
        "Pollutant", "Concentration (ug/m3 or umol/m2)", "Confidence Score (%)",
        "Est Release Time", "Detection Timestamp", "Assessed Fine (INR)",
        "Latitude", "Longitude", "Detection Source", "Logged At"
    ])
    for r in rows:
        writer.writerow([
            r["id"], r["factory_id"], r["factory_name"], r["registration_no"],
            r["pollutant"], r["concentration"], r["confidence_score"],
            r["est_release_time"], r["detection_timestamp"], r["penalty_inr"],
            r["plume_lat"], r["plume_lon"], r["source"], r["created_at"]
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="TNPCB_Continuous_Violations_Report.csv"'}
    )

@app.get("/api/night-violations/export-pdf")
def export_night_violations_pdf():
    """Export all compiled continuous violations as an official statutory PDF enforcement docket."""
    rows = db.get_all_night_violations()
    pdf_bytes = generate_curfew_violations_pdf(rows)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="TNPCB_Statutory_Docket_Continuous_Violations.pdf"'}
    )

@app.delete("/api/night-violations")
def clear_night_violations():
    """Clear nocturnal violations ledger."""
    db.clear_violations()
    return {"status": "success", "message": "Nocturnal violation ledger reset."}

def analyze_satellite_sounding(
    geojson_data: Dict[str, Any],
    factories: List[Dict[str, Any]],
    req_wspd: float = 4.0,
    req_wdir: float = 195.0
) -> Tuple[Dict[str, Any], float, List[Dict[str, Any]]]:
    """
    Extract peak plume anomaly from satellite GeoJSON sounding pass.
    Correlates with monitored industrial registry to pinpoint the culprit industry on the map.
    """
    features = geojson_data.get("features", [])
    if not features:
        raise ValueError("GeoJSON contains no features")

    candidates = []
    for f in features:
        geom = f.get("geometry", {})
        coords = geom.get("coordinates")
        if not coords:
            continue
        props = f.get("properties", {})
        
        so2 = props.get("so2_mol_m2") or props.get("SO2_column_number_density") or props.get("so2") or 0.0
        no2 = props.get("no2_mol_m2") or props.get("NO2_column_number_density") or props.get("no2") or 0.0
        
        if so2 >= no2 and so2 > 0:
            gas = "SO2"
            raw = float(so2)
        elif no2 > 0:
            gas = "NO2"
            raw = float(no2)
        else:
            raw = float(props.get("density") or props.get("val") or props.get("value") or 0.0)
            gas = props.get("gas_type") or "SO2"
            
        val_umol = raw * 1e6 if raw < 0.1 else raw
        
        if geom.get("type") == "Point":
            lon, lat = coords[0], coords[1]
        elif geom.get("type") == "Polygon":
            poly = coords[0]
            lon = sum(c[0] for c in poly) / len(poly)
            lat = sum(c[1] for c in poly) / len(poly)
        else:
            continue
            
        candidates.append({
            "lat": lat,
            "lon": lon,
            "gas_type": gas,
            "density_umol": val_umol,
            "timestamp": props.get("timestamp") or "2026-09-18T02:30:00Z"
        })
        
    if not candidates:
        raise ValueError("No point or polygon features with gas density data found")

    candidates.sort(key=lambda x: x["density_umol"], reverse=True)

    best_candidate = candidates[0]
    best_wdir = req_wdir
    best_suspects = []

    if factories:
        # Filter candidate plumes within ~10km of any registered industry
        corridor_candidates = []
        for c in candidates:
            for fact in factories:
                fgeom = fact.get("geometry", {})
                fc = fgeom.get("coordinates", [])
                if fgeom.get("type") == "Polygon" and fc:
                    flat, flon = fc[0][0][1], fc[0][0][0]
                elif fgeom.get("type") == "Point" and fc:
                    flat, flon = fc[1], fc[0]
                else:
                    continue
                if abs(c["lat"] - flat) < 0.09 and abs(c["lon"] - flon) < 0.09:
                    corridor_candidates.append(c)
                    break

        search_pool = corridor_candidates[:25] if corridor_candidates else candidates[:10]

        # 1. Test requested wind direction first
        for c in search_pool:
            sus = match_suspect_factories(c["lat"], c["lon"], c["gas_type"], c["density_umol"], req_wspd, req_wdir, c["timestamp"], factories)
            if sus and (not best_suspects or sus[0]["confidence_score"] > best_suspects[0]["confidence_score"]):
                best_suspects = sus
                best_candidate = c
                best_wdir = req_wdir
                if sus[0]["confidence_score"] > 80.0:
                    break

        # 2. If no high-confidence match, scan wind headings in 5-degree increments
        if not best_suspects or best_suspects[0]["confidence_score"] < 70.0:
            for c in search_pool:
                for wdir in range(0, 360, 5):
                    sus = match_suspect_factories(c["lat"], c["lon"], c["gas_type"], c["density_umol"], req_wspd, float(wdir), c["timestamp"], factories)
                    if sus and (not best_suspects or sus[0]["confidence_score"] > best_suspects[0]["confidence_score"]):
                        best_suspects = sus
                        best_candidate = c
                        best_wdir = float(wdir)
                        if sus[0]["confidence_score"] > 90.0:
                            break
                if best_suspects and best_suspects[0]["confidence_score"] > 90.0:
                    break

    return best_candidate, best_wdir, best_suspects

@app.post("/api/upload-satellite")
async def upload_satellite_geojson(
    file: UploadFile = File(...),
    wind_speed_mps: Optional[float] = None,
    wind_direction_deg: Optional[float] = None
):
    """
    Accepts Sentinel-5P or custom satellite GeoJSON sounding passes.
    Extracts peak plume anomaly, checks if any registered industry is located upwind,
    and returns pinpointed culprit coordinates and dispersion layers.
    """
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
        factories = load_factories_geojson(FACTORIES_PATH)
        
        req_wspd = wind_speed_mps if wind_speed_mps is not None else 4.0
        req_wdir = wind_direction_deg if wind_direction_deg is not None else 195.0
        
        peak, resolved_wdir, suspects = analyze_satellite_sounding(
            geojson_data=data,
            factories=factories,
            req_wspd=req_wspd,
            req_wdir=req_wdir
        )
        
        trajectory = calculate_inverse_trajectory(
            plume_lat=peak["lat"],
            plume_lon=peak["lon"],
            wind_speed_mps=req_wspd,
            wind_direction_deg=resolved_wdir,
            max_distance_m=8000.0,
            stability_class="F"
        )
        
        primary_culprit = suspects[0] if suspects else None
        
        # Auto-record in SQLite if detected during 10 PM - 6 AM curfew window
        if primary_culprit and db.is_curfew_hours(peak["timestamp"]):
            db.record_night_violation(
                factory=primary_culprit,
                pollutant=peak["gas_type"],
                concentration=peak["density_umol"],
                plume_lat=peak["lat"],
                plume_lon=peak["lon"],
                detection_timestamp=peak["timestamp"],
                source="satellite_upload"
            )

        return {
            "status": "success",
            "type": "satellite_plume",
            "spike": {
                "plume_lat": peak["lat"],
                "plume_lon": peak["lon"],
                "gas_type": peak["gas_type"],
                "gas_density_umol": round(peak["density_umol"], 1),
                "timestamp": peak["timestamp"],
                "total_points_analyzed": len(data.get("features", []))
            },
            "wind_vector": {
                "speed_mps": req_wspd,
                "direction_deg": resolved_wdir,
                "stability_class": "F"
            },
            "layers": {
                "spine": trajectory["spine_geojson"],
                "cone": trajectory["cone_geojson"],
                "heatmap_points": trajectory["heatmap_points"]
            },
            "suspects_count": len(suspects),
            "primary_culprit": primary_culprit,
            "suspects": suspects,
            "message": f"Pinpointed {primary_culprit['name']} ({primary_culprit['confidence_score']}% match) with wind heading {int(resolved_wdir)}°" if primary_culprit else f"Detected {peak['gas_type']} plume spike ({round(peak['density_umol'], 1)} µmol/m²). No registered industry found upwind in this corridor."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to analyze satellite GeoJSON: {str(e)}")

@app.post("/api/upload-factories")
async def upload_custom_factories(file: UploadFile = File(...)):
    """
    Allows uploading a new GeoJSON file.
    Automatically identifies whether it is a satellite plume pass or a factory catalog.
    """
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
        if "features" not in data:
            raise ValueError("Invalid GeoJSON: must contain 'features' list")
            
        sample_props = data["features"][0].get("properties", {}) if data["features"] else {}
        is_satellite_data = any(k in sample_props for k in ["_column_number_density", "no2_mol_m2", "so2_mol_m2"]) or ("name" not in sample_props and "category" not in sample_props)
        
        if is_satellite_data:
            factories = load_factories_geojson(FACTORIES_PATH)
            peak, resolved_wdir, suspects = analyze_satellite_sounding(
                geojson_data=data,
                factories=factories,
                req_wspd=4.0,
                req_wdir=195.0
            )
            trajectory = calculate_inverse_trajectory(
                plume_lat=peak["lat"],
                plume_lon=peak["lon"],
                wind_speed_mps=4.0,
                wind_direction_deg=resolved_wdir,
                max_distance_m=8000.0,
                stability_class="F"
            )
            primary_culprit = suspects[0] if suspects else None
            
            # Auto-record in SQLite if detected during 10 PM - 6 AM curfew window
            if primary_culprit and db.is_curfew_hours(peak["timestamp"]):
                db.record_night_violation(
                    factory=primary_culprit,
                    pollutant=peak["gas_type"],
                    concentration=peak["density_umol"],
                    plume_lat=peak["lat"],
                    plume_lon=peak["lon"],
                    detection_timestamp=peak["timestamp"],
                    source="satellite_upload"
                )

            return {
                "status": "success",
                "type": "satellite_plume",
                "spike": {
                    "plume_lat": peak["lat"],
                    "plume_lon": peak["lon"],
                    "gas_type": peak["gas_type"],
                    "gas_density_umol": round(peak["density_umol"], 1),
                    "timestamp": peak["timestamp"],
                    "total_points_analyzed": len(data.get("features", []))
                },
                "wind_vector": {
                    "speed_mps": 4.0,
                    "direction_deg": resolved_wdir,
                    "stability_class": "F"
                },
                "layers": {
                    "spine": trajectory["spine_geojson"],
                    "cone": trajectory["cone_geojson"],
                    "heatmap_points": trajectory["heatmap_points"]
                },
                "suspects_count": len(suspects),
                "primary_culprit": primary_culprit,
                "suspects": suspects,
                "message": f"Satellite pass analyzed! Pinpointed {primary_culprit['name']} ({primary_culprit['confidence_score']}% match)." if primary_culprit else f"Satellite pass analyzed: {round(peak['density_umol'], 1)} µmol/m² {peak['gas_type']} spike detected."
            }
        
        # Otherwise it's a factory catalog
        with open(FACTORIES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        return {
            "status": "success",
            "type": "factory_catalog",
            "message": f"Successfully updated locality with {len(data['features'])} factories.",
            "factory_count": len(data["features"])
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse GeoJSON: {str(e)}")

# =====================================================================
# RBAC MULTI-PORTAL SYSTEM API ENDPOINTS
# =====================================================================

class LoginRequest(BaseModel):
    email: str
    password: str

class UserCreateRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str
    factory_id: Optional[str] = None
    factory_name: Optional[str] = None
    industry_type: Optional[str] = None

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str
    factory_id: Optional[str] = None
    factory_name: Optional[str] = None
    industry_type: Optional[str] = None
    designation: Optional[str] = None
    industry_lat: Optional[float] = None
    industry_lon: Optional[float] = None
    industry_address: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    location_address: Optional[str] = None
    is_new_industry: Optional[bool] = False

class PlumeOverrideRequest(BaseModel):
    spike_id: str
    verified: bool
    override_culprit: Optional[str] = None
    notes: Optional[str] = None

class BroadcastRequest(BaseModel):
    active: bool
    title: str
    message: str
    severity: Optional[str] = "warning"

class IssueNoticeRequest(BaseModel):
    factory_id: str
    violation_type: str
    fine_inr: int
    evidence_summary: str

class CitizenReportRequest(BaseModel):
    citizen_name: str
    citizen_email: str
    odor_level: int = Field(..., ge=1, le=5)
    pollutant_type: str
    location: str
    lat: float
    lon: float
    description: str
    photo_url: Optional[str] = None

# --- AUTH ROUTES ---

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    user = auth.get_user_by_email(req.email)
    if not user or not auth.verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Check verification status for registered accounts
    user_status = user.get("status", "approved")
    if user_status == "pending":
        raise HTTPException(
            status_code=403,
            detail="Account pending administrator verification. Please wait for the TNPCB Admin to approve your registration."
        )
    elif user_status == "rejected":
        raise HTTPException(
            status_code=403,
            detail="Account registration was rejected by the TNPCB Administrator."
        )

    token = auth.create_session(user)
    sanitized = sanitize_user(user)
    log_audit_action(
        user_email=user["email"],
        user_name=user["name"],
        role=user["role"],
        action="AUTH_LOGIN",
        details=f"User {user['name']} ({user['role']}) logged in successfully."
    )
    return {
        "status": "success",
        "token": token,
        "user": sanitized
    }

@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    role = req.role.strip()
    if role not in ["industry_manager", "regulator", "citizen"]:
        raise HTTPException(status_code=400, detail="Invalid role specified")

    is_new = bool(req.is_new_industry or req.factory_id == "OTHER")
    initial_status = "pending" if role in ["industry_manager", "regulator"] else "approved"

    # For new industries, both Government PCB officer and Admin must verify
    admin_verified = False
    gov_verified = False if is_new else True

    eff_lat = req.location_lat if req.location_lat is not None else req.industry_lat
    eff_lon = req.location_lon if req.location_lon is not None else req.industry_lon
    eff_addr = req.location_address or req.industry_address

    new_user = auth.create_user(
        email=req.email,
        password=req.password,
        name=req.name,
        role=role,
        factory_id=None if is_new else req.factory_id,
        factory_name=req.factory_name,
        status=initial_status,
        designation=req.designation,
        industry_type=req.industry_type,
        industry_lat=eff_lat,
        industry_lon=eff_lon,
        industry_address=eff_addr,
        location_lat=eff_lat,
        location_lon=eff_lon,
        location_address=eff_addr,
        is_new_industry=is_new,
        admin_verified=admin_verified,
        gov_verified=gov_verified
    )

    log_audit_action(
        user_email=req.email,
        user_name=req.name,
        role=role,
        action="USER_REGISTERED",
        details=f"New user registered ({role}). New Industry: {is_new}. Status: {initial_status}."
    )

    msg = (
        "Registration submitted! New industrial units require dual verification by both the Government PCB Regulator and the Administrator before being mapped on Google Maps."
        if is_new
        else (
            "Registration submitted! Your account requires verification by the TNPCB Administrator before login."
            if initial_status == "pending"
            else "Registration successful! You may now sign in."
        )
    )

    return {
        "status": "success",
        "user": new_user,
        "requires_verification": initial_status == "pending",
        "message": msg
    }

@app.get("/api/auth/me")
def auth_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {
        "status": "success",
        "user": current_user
    }

@app.post("/api/auth/logout")
def auth_logout(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else request.query_params.get("token")
    if token:
        auth.delete_session(token)
    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="AUTH_LOGOUT",
        details=f"User {current_user['name']} logged out."
    )
    return {
        "status": "success",
        "detail": "Logged out successfully"
    }

# --- SUPER ADMIN ROUTES ---

@app.get("/api/admin/users", dependencies=[Depends(require_roles(["super_admin"]))])
def admin_list_users():
    users = [sanitize_user(u) for u in auth.load_users()]
    return {
        "status": "success",
        "users": users,
        "total": len(users)
    }

@app.post("/api/admin/users")
def admin_create_user(
    req: UserCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(["super_admin"]))
):
    new_user = auth.create_user(
        email=req.email,
        password=req.password,
        name=req.name,
        role=req.role,
        factory_id=req.factory_id,
        factory_name=req.factory_name,
        status="approved",
        industry_type=req.industry_type
    )
    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="USER_CREATED",
        details=f"Created user {new_user['email']} with role {new_user['role']}."
    )
    return {
        "status": "success",
        "user": new_user
    }

@app.post("/api/admin/users/{user_id}/approve", dependencies=[Depends(require_roles(["super_admin"]))])
def admin_approve_user(
    user_id: str,
    force_both: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    target = auth.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    is_new = target.get("is_new_industry", False)
    if is_new:
        if force_both:
            target = auth.verify_user_dual(user_id, "gov")
        target = auth.verify_user_dual(user_id, "admin")

        new_feature = None
        dual_complete = target.get("status") == "approved"
        if dual_complete:
            new_feature = add_verified_factory_to_geojson(target)
            if new_feature:
                users = auth.load_users()
                for u in users:
                    if u.get("id") == user_id:
                        u["factory_id"] = new_feature["properties"]["id"]
                        break
                auth.save_users(users)
                target["factory_id"] = new_feature["properties"]["id"]

        log_audit_action(
            user_email=current_user["email"],
            user_name=current_user["name"],
            role=current_user["role"],
            action="USER_ADMIN_VERIFIED",
            details=f"Admin approved {target['email']}. Dual verification complete: {dual_complete}."
        )

        msg = (
            f"Dual verification complete! {target.get('factory_name')} added to Google Maps."
            if dual_complete
            else f"Admin approved {target['name']}. Awaiting Government PCB Regulator verification."
        )

        return {
            "status": "success",
            "user": sanitize_user(target),
            "dual_verified": dual_complete,
            "factory": new_feature,
            "message": msg
        }
    else:
        user = auth.update_user_status(user_id, "approved")
        log_audit_action(
            user_email=current_user["email"],
            user_name=current_user["name"],
            role=current_user["role"],
            action="USER_APPROVED",
            details=f"Approved registration for {user['email']} ({user['role']})."
        )
        return {"status": "success", "user": user, "message": f"User {user['email']} approved successfully."}

@app.post("/api/admin/users/{user_id}/reject", dependencies=[Depends(require_roles(["super_admin"]))])
def admin_reject_user(user_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    user = auth.update_user_status(user_id, "rejected")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="USER_REJECTED",
        details=f"Rejected registration for {user['email']} ({user['role']})."
    )
    return {"status": "success", "user": user, "message": f"User {user['email']} rejected."}

@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_roles(["super_admin"]))
):
    target = auth.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["id"] == current_user.get("id"):
        raise HTTPException(status_code=400, detail="Cannot delete current active super_admin account")
    
    success = auth.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Failed to delete user")
    
    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="USER_DELETED",
        details=f"Deleted user account {target['email']} ({target['name']})."
    )
    return {
        "status": "success",
        "detail": f"User {target['email']} deleted successfully"
    }

@app.post("/api/admin/override-plume")
def admin_override_plume(
    req: PlumeOverrideRequest,
    current_user: Dict[str, Any] = Depends(require_roles(["super_admin"]))
):
    state = load_system_state()
    overrides = state.setdefault("plume_overrides", {})
    overrides[req.spike_id] = {
        "verified": req.verified,
        "override_culprit": req.override_culprit,
        "notes": req.notes,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_by": current_user["email"]
    }
    save_system_state(state)
    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="PLUME_OVERRIDE",
        details=f"Satellite plume spike {req.spike_id} override set: verified={req.verified}, culprit={req.override_culprit}."
    )
    return {
        "status": "success",
        "spike_id": req.spike_id,
        "override": overrides[req.spike_id]
    }

@app.get("/api/admin/settings", dependencies=[Depends(require_roles(["super_admin"]))])
def admin_get_settings():
    state = load_system_state()
    return {
        "status": "success",
        "settings": state.get("settings", {})
    }

@app.post("/api/admin/settings")
def admin_update_settings(
    settings_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles(["super_admin"]))
):
    state = load_system_state()
    current_settings = state.setdefault("settings", {})
    current_settings.update(settings_data)
    save_system_state(state)
    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="SETTINGS_UPDATED",
        details=f"Thresholds & system parameters updated: {list(settings_data.keys())}."
    )
    return {
        "status": "success",
        "settings": current_settings
    }

@app.get("/api/admin/logs", dependencies=[Depends(require_roles(["super_admin"]))])
def admin_get_logs(role: Optional[str] = None):
    state = load_system_state()
    logs = state.get("audit_log", [])
    if role:
        logs = [l for l in logs if l.get("role") == role]
    return {
        "status": "success",
        "logs": logs,
        "total": len(logs)
    }

@app.get("/api/admin/government-logs", dependencies=[Depends(require_roles(["super_admin"]))])
def admin_get_government_logs():
    """Returns Government Regulator actions to display as Government Logs on the Admin page."""
    state = load_system_state()
    logs = [l for l in state.get("audit_log", []) if l.get("role") == "regulator"]
    return {
        "status": "success",
        "logs": logs,
        "total": len(logs)
    }

@app.post("/api/admin/broadcast")
def admin_set_broadcast(
    req: BroadcastRequest,
    current_user: Dict[str, Any] = Depends(require_roles(["super_admin"]))
):
    state = load_system_state()
    broadcast = {
        "active": req.active,
        "title": req.title,
        "message": req.message,
        "severity": req.severity,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_by": f"{current_user['name']} ({current_user['role']})"
    }
    state["broadcast_message"] = broadcast
    save_system_state(state)
    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="BROADCAST_UPDATED",
        details=f"Broadcast active={req.active}, title='{req.title}'."
    )
    return {
        "status": "success",
        "broadcast": broadcast
    }

# --- INDUSTRY MANAGER ROUTES (SCOPED STRICTLY TO MANAGER'S FACTORY) ---

@app.get("/api/manager/telemetry")
def manager_get_telemetry(current_user: Dict[str, Any] = Depends(require_roles(["industry_manager", "super_admin"]))):
    factory_id = current_user.get("factory_id") or "FAC-01"
    
    # Load factory details
    factories = load_factories_geojson(FACTORIES_PATH)
    features = factories if isinstance(factories, list) else factories.get("features", [])
    target_fac = None
    for f in features:
        if f.get("properties", {}).get("id") == factory_id:
            target_fac = f.get("properties", {})
            break
    
    factory_name = target_fac.get("name") if target_fac else current_user.get("factory_name", "Ranipet Tannery Consortium - Unit 4B")
    
    # 24-hour CEMS simulated hourly curve with higher values during curfew (22:00 to 06:00)
    now = datetime.now()
    sparklines = []
    for h in range(24, 0, -1):
        hour_val = (now.hour - h) % 24
        is_curfew = (hour_val >= 22 or hour_val < 6)
        base_so2 = 68.4 if is_curfew else 34.2
        base_h2s = 14.1 if is_curfew else 5.8
        sparklines.append({
            "hour": f"{hour_val:02d}:00",
            "is_curfew": is_curfew,
            "so2_ugm3": round(base_so2 + ((h * 7) % 15) - 6.5, 1),
            "h2s_ugm3": round(base_h2s + ((h * 3) % 6) - 2.8, 1),
            "stack_temp_c": round(145.0 + ((h * 2) % 10), 1),
            "flow_rate_m3s": round(17.5 + ((h * 11) % 4) * 0.5, 1)
        })

    live_sensors = {
        "so2_ugm3": 44.8,
        "h2s_ugm3": 8.5,
        "stack_temperature_c": 149.2,
        "flue_gas_flow_m3s": 18.2,
        "cems_status": "ONLINE - CONTINUOUS TRANSMISSION",
        "cems_serial": "ABB-AO2000-CEMS-9941",
        "last_calibration": "2026-09-12",
        "next_statutory_audit": "2026-10-15"
    }

    return {
        "status": "success",
        "factory_id": factory_id,
        "factory_name": factory_name,
        "registration_no": target_fac.get("registration_no", "TNPCB/RN/TAN-0491") if target_fac else "TNPCB/RN/TAN-0491",
        "category": target_fac.get("category", "Tannery") if target_fac else "Tannery",
        "stack_height_m": target_fac.get("stack_height_m", 22.0) if target_fac else 22.0,
        "live_sensors": live_sensors,
        "hourly_sparklines_24h": sparklines,
        "thresholds": {
            "so2_limit_ugm3": 80.0,
            "h2s_limit_ugm3": 15.0,
            "stack_temp_max_c": 180.0
        },
        "curfew_compliance_rate": 93.8
    }

@app.get("/api/manager/fines")
def manager_get_fines(current_user: Dict[str, Any] = Depends(require_roles(["industry_manager", "super_admin"]))):
    factory_id = current_user.get("factory_id") or "FAC-01"
    
    # Night violations from SQLite (deduplicated by event date/id)
    all_violations = db.get_all_night_violations()
    raw_violations = [v for v in all_violations if v.get("factory_id") == factory_id]
    
    # ponytail: deduplicate to keep at most 1 violation per incident date so fines don't stack indefinitely
    seen_dates = set()
    scoped_violations = []
    for v in raw_violations:
        d_key = (v.get("detection_timestamp") or "")[:10]
        if d_key not in seen_dates:
            seen_dates.add(d_key)
            scoped_violations.append(v)
    
    # Issued notices from system state
    state = load_system_state()
    all_notices = state.get("issued_notices", [])
    scoped_notices = [n for n in all_notices if n.get("factory_id") == factory_id]
    
    total_penalties = sum(v.get("penalty_inr", 0) for v in scoped_violations)
    
    return {
        "status": "success",
        "factory_id": factory_id,
        "violations_count": len(scoped_violations),
        "notices_count": len(scoped_notices),
        "total_penalty_assessed_inr": total_penalties,
        "violations": scoped_violations,
        "notices": scoped_notices
    }

@app.get("/api/manager/compliance-report")
def manager_get_compliance_report(current_user: Dict[str, Any] = Depends(require_roles(["industry_manager", "super_admin"]))):
    factory_id = current_user.get("factory_id") or "FAC-01"
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    return {
        "status": "success",
        "report_id": f"REP-COMP-{factory_id}-{datetime.utcnow().strftime('%Y%m%d')}",
        "generated_at": now_str,
        "factory_id": factory_id,
        "factory_name": current_user.get("factory_name", "Ranipet Tannery Consortium - Unit 4B"),
        "compliance_officer": current_user.get("name", "K. Ramanathan"),
        "executive_summary": "Internal industrial compliance audit generated under TNPCB Continuous Emission Monitoring standards.",
        "metrics": {
            "cems_uptime_pct": 99.1,
            "nocturnal_curfew_adherence_pct": 93.8,
            "scrubber_efficiency_pct": 96.4,
            "effluent_treatment_status": "Operational (ZLD Active)"
        },
        "recommendations": [
            "Maintain secondary alkaline scrubber pump at 100% capacity during 22:00 - 06:00 IST nocturnal thermal inversion.",
            "Schedule quarterly sensor recalibration before October 15, 2026.",
            "Maintain automated data telemetry link with TNPCB Care Air Centre."
        ]
    }

# --- REGULATOR ROUTES ---

@app.get("/api/regulator/flagged-plumes", dependencies=[Depends(require_roles(["regulator", "super_admin"]))])
def regulator_get_flagged_plumes():
    spikes = []
    if os.path.exists(SPIKES_PATH):
        with open(SPIKES_PATH, "r", encoding="utf-8") as f:
            spikes = json.load(f)
            
    state = load_system_state()
    overrides = state.get("plume_overrides", {})
    
    enriched = []
    # 1. Preset satellite soundings
    for s in spikes:
        item = dict(s)
        spike_id = s.get("id")
        item["is_curfew_violation"] = db.is_curfew_hours(s.get("timestamp"))
        item["override_status"] = overrides.get(spike_id, {"verified": False})
        item["evidence_dossier"] = {
            "satellite_sensor": "TROPOMI Sentinel-5P (Level 2 Offline)",
            "gas_signature": s.get("gas_type", "SO2"),
            "column_density_umol": s.get("gas_density_umol"),
            "wind_consistency_score": 92.4,
            "proximity_score": 95.8,
            "crosswind_offset_m": 42.0,
            "legal_standing": "Sufficient corroboration for Section 21 Show-Cause Notice"
        }
        enriched.append(item)

    # 2. Dynamic 24/7 continuous violations logged in SQLite
    try:
        db_viols = db.get_all_night_violations()
        for v in db_viols:
            v_id = f"VIOL-{v['id']:04d}"
            if any(x.get("id") == v_id for x in enriched):
                continue
            factory_name = v.get("factory_name", "Industrial Unit")
            enriched.insert(0, {
                "id": v_id,
                "title": f"Exceedance Event: {factory_name}",
                "timestamp": v.get("detection_timestamp") or v.get("created_at"),
                "gas_type": v.get("pollutant", "SO2"),
                "gas_density_umol": round(v.get("concentration", 75.0), 1),
                "attributed_culprit": factory_name,
                "factory_id": v.get("factory_id", "FAC-01"),
                "confidence_pct": round(v.get("confidence_score", 95.0)),
                "sensor": f"24/7 Sounder ({v.get('source', 'realtime')})",
                "is_curfew_violation": True,
                "override_status": overrides.get(v_id, {"verified": False}),
                "evidence_dossier": {
                    "satellite_sensor": f"Continuous Atmospheric Sounder ({v.get('source', 'realtime')})",
                    "gas_signature": v.get("pollutant", "SO2"),
                    "column_density_umol": round(v.get("concentration", 75.0), 1),
                    "wind_consistency_score": 93.5,
                    "proximity_score": round(v.get("confidence_score", 95.0)),
                    "crosswind_offset_m": 35.0,
                    "legal_standing": "Logged in Statutory 24/7 Exceedance Registry"
                }
            })
    except Exception as e:
        print(f"Error enriching regulator flagged plumes with db violations: {e}")
        
    return {
        "status": "success",
        "flagged_plumes": enriched,
        "total": len(enriched)
    }

@app.post("/api/regulator/issue-notice")
def regulator_issue_notice(
    req: IssueNoticeRequest,
    current_user: Dict[str, Any] = Depends(require_roles(["regulator", "super_admin"]))
):
    state = load_system_state()
    notices = state.setdefault("issued_notices", [])
    
    # Lookup factory details
    factories = load_factories_geojson(FACTORIES_PATH)
    features = factories if isinstance(factories, list) else factories.get("features", [])
    target = None
    for f in features:
        if f.get("properties", {}).get("id") == req.factory_id:
            target = f.get("properties", {})
            break
            
    factory_name = target.get("name", req.factory_id) if target else req.factory_id
    reg_no = target.get("registration_no", "TNPCB/RN/IND-9900") if target else "TNPCB/RN/IND-9900"
    
    notice_id = f"NOT-2026-{len(notices) + 1:03d}"
    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    notice_record = {
        "id": notice_id,
        "factory_id": req.factory_id,
        "factory_name": factory_name,
        "registration_no": reg_no,
        "violation_type": req.violation_type,
        "fine_inr": req.fine_inr,
        "issued_by": f"{current_user['name']} ({current_user['role']})",
        "issued_by_email": current_user["email"],
        "timestamp": now_iso,
        "evidence_summary": req.evidence_summary,
        "pdf_filename": f"Statutory_Notice_{req.factory_id}_{notice_id}.pdf"
    }
    
    notices.insert(0, notice_record)
    save_system_state(state)
    
    # Record into SQLite violations database
    if target:
        db.record_night_violation(
            factory={
                "factory_id": req.factory_id,
                "name": factory_name,
                "registration_no": reg_no,
                "confidence_score": 95.0,
                "calculated_fine_inr": req.fine_inr,
                "est_release_time": "Nocturnal Sounding"
            },
            pollutant="SO2",
            concentration=req.fine_inr / 1000.0,
            plume_lat=target.get("coordinates", [12.928, 79.330])[1] if "coordinates" in target else 12.928,
            plume_lon=target.get("coordinates", [12.928, 79.330])[0] if "coordinates" in target else 79.330,
            detection_timestamp=now_iso,
            source="regulator_statutory_notice"
        )
        
    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="STATUTORY_NOTICE_ISSUED",
        details=f"Issued Section 21 notice {notice_id} to {factory_name} (Fine: ₹{req.fine_inr:,})."
    )
    
    return {
        "status": "success",
        "notice": notice_record
    }

@app.get("/api/regulator/notices", dependencies=[Depends(require_roles(["regulator", "super_admin"]))])
def regulator_get_notices():
    state = load_system_state()
    notices = state.get("issued_notices", [])
    return {
        "status": "success",
        "notices": notices,
        "total": len(notices)
    }

@app.get("/api/regulator/settings", dependencies=[Depends(require_roles(["regulator", "super_admin"]))])
def regulator_get_settings():
    """Read-only access for regulators to view current operational thresholds."""
    state = load_system_state()
    return {
        "status": "success",
        "settings": state.get("settings", {}),
        "access": "read_only"
    }

@app.post("/api/regulator/settings", dependencies=[Depends(require_roles(["super_admin"]))])
def regulator_settings_forbidden():
    """Regulator POST is rejected with 403 Forbidden as per plan specification."""
    raise HTTPException(status_code=403, detail="Forbidden: Regulators have read-only access to settings")

@app.get("/api/regulator/pending-industries", dependencies=[Depends(require_roles(["regulator", "super_admin"]))])
def regulator_get_pending_industries():
    """List new industries pending government PCB verification."""
    users = auth.load_users()
    pending = [
        sanitize_user(u) for u in users
        if u.get("is_new_industry") and (not u.get("gov_verified") or u.get("status") == "pending")
    ]
    return {"status": "success", "pending": pending, "count": len(pending)}

@app.post("/api/regulator/verify-industry/{user_id}", dependencies=[Depends(require_roles(["regulator", "super_admin"]))])
def regulator_verify_industry(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    target = auth.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target = auth.verify_user_dual(user_id, "gov")
    dual_complete = target.get("status") == "approved"
    new_feature = None
    if dual_complete:
        new_feature = add_verified_factory_to_geojson(target)
        if new_feature:
            users = auth.load_users()
            for u in users:
                if u.get("id") == user_id:
                    u["factory_id"] = new_feature["properties"]["id"]
                    break
            auth.save_users(users)
            target["factory_id"] = new_feature["properties"]["id"]

    log_audit_action(
        user_email=current_user["email"],
        user_name=current_user["name"],
        role=current_user["role"],
        action="INDUSTRY_GOV_VERIFIED",
        details=f"Government PCB officer {current_user['name']} verified {target.get('factory_name')}. Dual complete: {dual_complete}."
    )

    msg = (
        f"Dual verification complete! {target.get('factory_name')} verified and added to Google Maps."
        if dual_complete
        else f"Government PCB verification recorded for {target.get('factory_name')}. Awaiting Super Admin approval."
    )

    return {
        "status": "success",
        "user": sanitize_user(target),
        "dual_verified": dual_complete,
        "factory": new_feature,
        "message": msg
    }

@app.get("/api/regulator/admin-logs", dependencies=[Depends(require_roles(["regulator", "super_admin"]))])
def regulator_get_admin_logs():
    """Returns Super Admin activity and oversight logs for display on the Government portal."""
    state = load_system_state()
    logs = [l for l in state.get("audit_log", []) if l.get("role") == "super_admin"]
    return {
        "status": "success",
        "logs": logs,
        "total": len(logs)
    }

# --- PUBLIC & CITIZEN PORTAL ROUTES ---

@app.get("/api/public/pollution-map")
def get_public_pollution_map():
    raw = load_factories_geojson(FACTORIES_PATH)
    features = raw if isinstance(raw, list) else raw.get("features", [])
    masked_features = []
    for f in features:
        p = f.get("properties", {})
        reg_no = p.get("registration_no", p.get("id", "TNPCB-IND"))
        masked_p = {
            "id": p.get("id"),
            "masked_name": f"Industrial Unit [{reg_no}]",
            "category": p.get("category", "General Industrial"),
            "emissions": p.get("emissions", ["SO2"]),
            "stack_height_m": p.get("stack_height_m", 25.0),
            "regulatory_status": "Active Under Air Act Section 21",
            "health_buffer_zone_m": 250
        }
        masked_features.append({
            "type": "Feature",
            "properties": masked_p,
            "geometry": f.get("geometry")
        })
        
    return {
        "type": "FeatureCollection",
        "name": "Ranipet_Public_Industrial_Buffer_Map",
        "features": masked_features,
        "total_units": len(masked_features)
    }

@app.get("/api/public/air-quality")
def get_public_air_quality():
    return {
        "status": "success",
        "corridor": "Ranipet SIPCOT & Palar River Basin",
        "aqi": 168,
        "category": "Unhealthy",
        "category_color": "#ef4444",
        "dominant_pollutant": "SO2 (Sulfur Dioxide)",
        "pollutant_levels": {
            "so2_ugm3": 78.4,
            "pm25_ugm3": 62.1,
            "pm10_ugm3": 114.5,
            "no2_ugm3": 38.0
        },
        "health_advisory": [
            "Children, elderly, and individuals with respiratory conditions should minimize prolonged outdoor exertion.",
            "Keep residential windows closed during nocturnal thermal inversion hours (10 PM - 6 AM).",
            "Wear N95/FFP2 protective face coverings when traveling through SIPCOT Phase I & II corridors."
        ],
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }

@app.get("/api/public/citizen-reports")
def get_public_citizen_reports():
    state = load_system_state()
    grievances = state.get("citizen_grievances", [])
    return {
        "status": "success",
        "grievances": grievances,
        "total": len(grievances)
    }

@app.post("/api/public/citizen-reports")
def submit_citizen_report(req: CitizenReportRequest):
    state = load_system_state()
    grievances = state.setdefault("citizen_grievances", [])
    
    new_id = f"GRV-{len(grievances) + 1:04d}"
    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    grievance = {
        "id": new_id,
        "citizen_name": req.citizen_name,
        "citizen_email": req.citizen_email,
        "odor_level": req.odor_level,
        "pollutant_type": req.pollutant_type,
        "location": req.location,
        "lat": round(req.lat, 4),
        "lon": round(req.lon, 4),
        "description": req.description,
        "photo_url": req.photo_url or "simulation_plume_night.jpg",
        "timestamp": now_iso,
        "status": "Under Investigation",
        "assigned_to": "P. Soundararajan (TNPCB District Officer)"
    }
    
    grievances.insert(0, grievance)
    save_system_state(state)
    
    log_audit_action(
        user_email=req.citizen_email,
        user_name=req.citizen_name,
        role="citizen",
        action="CITIZEN_GRIEVANCE_FILED",
        details=f"Filed odor level {req.odor_level}/5 complaint at {req.location}."
    )
    
    return {
        "status": "success",
        "grievance": grievance,
        "message": "Grievance registered and dispatched to TNPCB Mobile Inspection Unit."
    }

@app.get("/api/public/broadcast")
def get_public_broadcast():
    state = load_system_state()
    return {
        "status": "success",
        "broadcast": state.get("broadcast_message", {})
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting PlumeBacktrace AI Server on http://localhost:8000 ...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
