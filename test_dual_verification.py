"""
PlumeBacktrace AI - Self-Contained Verification Check
Validates:
1. Industry manager registration with "OTHER" / new facility + GPS coordinates.
2. Dual verification workflow (Government PCB Regulator + Super Admin in both orders).
3. Automatic commitment of verified new industry to factories.geojson (Point feature) and /api/factories.
"""
import os
import json
import secrets
from main import (
    auth_register,
    auth_login,
    regulator_get_pending_industries,
    regulator_verify_industry,
    admin_approve_user,
    get_factories,
    RegisterRequest,
    LoginRequest,
    FACTORIES_PATH
)
import auth
from fastapi import HTTPException

def run_checks():
    reg_user = auth.get_user_by_email("regulator@tnpcb.gov.in")
    admin_user = auth.get_user_by_email("admin@plume.ai")
    assert reg_user and admin_user, "Default regulator or admin user missing in users.json"

    # --- Test 1: Gov verifies first, Admin approves second ---
    email1 = f"mgr1_{secrets.token_hex(3)}@industry.com"
    ind1 = f"GovFirst Chemical {secrets.token_hex(2).upper()}"
    lat1, lon1 = 12.9240, 79.3290

    res1 = auth_register(RegisterRequest(
        name="Manager One",
        email=email1,
        password="password123",
        role="industry_manager",
        factory_id="OTHER",
        factory_name=ind1,
        industry_type="Tannery & Leather Processing",
        industry_lat=lat1,
        industry_lon=lon1,
        industry_address="Ranipet Leather Corridor",
        is_new_industry=True
    ))
    u1 = res1["user"]
    assert u1["status"] == "pending"
    assert u1["is_new_industry"] is True

    # Gov verifies
    r_gov1 = regulator_verify_industry(user_id=u1["id"], current_user=reg_user)
    assert r_gov1["dual_verified"] is False
    assert r_gov1["user"]["gov_verified"] is True
    assert r_gov1["user"]["status"] == "pending"

    # Admin approves -> dual complete -> added to geojson
    r_adm1 = admin_approve_user(user_id=u1["id"], current_user=admin_user)
    assert r_adm1["dual_verified"] is True
    assert r_adm1["user"]["status"] == "approved"
    assert r_adm1["factory"]["properties"]["name"] == ind1
    assert r_adm1["factory"]["geometry"]["coordinates"] == [lon1, lat1]

    # --- Test 2: Admin approves first, Gov verifies second ---
    email2 = f"mgr2_{secrets.token_hex(3)}@industry.com"
    ind2 = f"AdminFirst Petrochem {secrets.token_hex(2).upper()}"
    lat2, lon2 = 12.9295, 79.3340

    res2 = auth_register(RegisterRequest(
        name="Manager Two",
        email=email2,
        password="password123",
        role="industry_manager",
        factory_id="OTHER",
        factory_name=ind2,
        industry_type="Chemical & Petrochemical Manufacturing",
        industry_lat=lat2,
        industry_lon=lon2,
        industry_address="SIPCOT Phase II Corridor",
        is_new_industry=True
    ))
    u2 = res2["user"]

    # Admin approves
    r_adm2 = admin_approve_user(user_id=u2["id"], current_user=admin_user)
    assert r_adm2["dual_verified"] is False
    assert r_adm2["user"]["admin_verified"] is True
    assert r_adm2["user"]["status"] == "pending"

    # Gov verifies -> dual complete -> added to geojson
    r_gov2 = regulator_verify_industry(user_id=u2["id"], current_user=reg_user)
    assert r_gov2["dual_verified"] is True
    assert r_gov2["user"]["status"] == "approved"
    assert r_gov2["factory"]["properties"]["name"] == ind2
    assert r_gov2["factory"]["geometry"]["coordinates"] == [lon2, lat2]

    # Check factories list reflects both
    facts = get_factories()["features"]
    names = [f["properties"]["name"] for f in facts]
    assert ind1 in names and ind2 in names, "Factories not found in get_factories()"

    # --- Test 3: Government Regulator Signup with Exact Location & 10 km Surveillance Perimeter ---
    from main import search_so2_radius
    gov_email = f"gov_station_{secrets.token_hex(3)}@tnpcb.gov.in"
    gov_res = auth_register(RegisterRequest(
        name="Officer Surveillance",
        email=gov_email,
        password="govPassword123",
        role="regulator",
        designation="TNPCB District Environmental Office",
        location_lat=12.9252,
        location_lon=79.3318,
        location_address="TNPCB District Environmental Office, Ranipet Industrial Belt"
    ))
    gov_u = gov_res["user"]
    assert gov_u["location_lat"] == 12.9252
    assert gov_u["location_lon"] == 79.3318
    assert "Ranipet" in gov_u["location_address"]

    # Execute 10 km radial surveillance sweep using government station location
    perim = search_so2_radius(lat=gov_u["location_lat"], lon=gov_u["location_lon"], radius_km=10.0)
    assert perim["radius_km"] == 10.0
    assert perim["exceeding_count"] > 0, "Expected exceeding industries in 10 km industrial zone"
    for exc in perim["exceeding_industries"]:
        assert exc["distance_km"] <= 10.0, f"Industry {exc['name']} is outside 10 km perimeter ({exc['distance_km']} km)"
        assert exc["so2_ugm3"] >= 20.0, f"Industry {exc['name']} does not exceed CPCB limit ({exc['so2_ugm3']})"
        assert exc["fine_inr"] > 0, f"Industry {exc['name']} must have a statutory fine tag"
        assert exc["lat"] is not None and exc["lon"] is not None

    # Cleanup test records
    auth.delete_user(u1["id"])
    auth.delete_user(u2["id"])
    auth.delete_user(gov_u["id"])
    with open(FACTORIES_PATH, "r", encoding="utf-8") as f:
        fdata = json.load(f)
    fdata["features"] = [f for f in fdata.get("features", []) if f["properties"]["name"] not in (ind1, ind2)]
    with open(FACTORIES_PATH, "w", encoding="utf-8") as f:
        json.dump(fdata, f, indent=2)

    print("PASS: Dual verification, government exact location signup, and 10 km perimeter exceedance checks succeeded.")

if __name__ == "__main__":
    run_checks()

