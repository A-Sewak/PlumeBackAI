"""
PlumeBacktrace AI - Role-Based Access Control (RBAC) & Authentication Module
Zero-dependency session store, password hashing, user CRUD, audit logging,
and role gatekeeping dependencies using Python stdlib and FastAPI.
"""

import os
import json
import secrets
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import Request, Header, HTTPException, Depends

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_PATH = os.path.join(DATA_DIR, "users.json")
STATE_PATH = os.path.join(DATA_DIR, "system_state.json")

# In-memory session store: token -> user dict
SESSIONS: Dict[str, Dict[str, Any]] = {}

def save_json_safely(filepath: str, data: Any) -> None:
    """Atomic write to JSON file: write to tmp file then atomically replace."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_path = f"{filepath}.tmp_{secrets.token_hex(4)}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, filepath)

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hash password using SHA-256 with 16-char hex salt."""
    if not salt:
        salt = secrets.token_hex(8)
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify plain password against stored salt:hash string."""
    if not stored_hash:
        return False
    if ":" in stored_hash:
        salt, expected_hash = stored_hash.split(":", 1)
        calc_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return calc_hash == expected_hash
    # Fallback in case raw password was saved
    return password == stored_hash

def load_users() -> List[Dict[str, Any]]:
    """Load user records from data/users.json."""
    if not os.path.exists(USERS_PATH):
        return []
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_users(users: List[Dict[str, Any]]) -> None:
    """Safely persist user records to data/users.json."""
    save_json_safely(USERS_PATH, users)

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Find user record by email (case-insensitive)."""
    clean = email.strip().lower()
    for u in load_users():
        if u.get("email", "").strip().lower() == clean:
            return u
    return None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Find user record by unique ID."""
    for u in load_users():
        if u.get("id") == user_id:
            return u
    return None

def sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Return user dict without sensitive password hashes."""
    clean = dict(user)
    clean.pop("password_hash", None)
    return clean

def create_user(
    email: str,
    password: str,
    name: str,
    role: str,
    factory_id: Optional[str] = None,
    factory_name: Optional[str] = None,
    status: str = "approved",
    designation: Optional[str] = None,
    industry_type: Optional[str] = None,
    industry_lat: Optional[float] = None,
    industry_lon: Optional[float] = None,
    industry_address: Optional[str] = None,
    location_lat: Optional[float] = None,
    location_lon: Optional[float] = None,
    location_address: Optional[str] = None,
    is_new_industry: bool = False,
    admin_verified: bool = False,
    gov_verified: bool = False
) -> Dict[str, Any]:
    """Create a new user and safely persist to disk."""
    if get_user_by_email(email):
        raise HTTPException(status_code=400, detail="User with this email already exists")

    eff_lat = location_lat if location_lat is not None else industry_lat
    eff_lon = location_lon if location_lon is not None else industry_lon
    eff_addr = location_address or industry_address

    users = load_users()
    new_id = f"USR-{len(users) + 1:03d}"
    new_user = {
        "id": new_id,
        "email": email.strip().lower(),
        "password_hash": hash_password(password),
        "name": name.strip(),
        "role": role.strip(),
        "status": status,
        "factory_id": factory_id,
        "factory_name": factory_name,
        "industry_type": industry_type,
        "designation": designation,
        "industry_lat": eff_lat,
        "industry_lon": eff_lon,
        "industry_address": eff_addr,
        "location_lat": eff_lat,
        "location_lon": eff_lon,
        "location_address": eff_addr,
        "is_new_industry": is_new_industry,
        "admin_verified": admin_verified,
        "gov_verified": gov_verified,
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    users.append(new_user)
    save_users(users)
    return sanitize_user(new_user)

def verify_user_dual(user_id: str, verifier: str) -> Optional[Dict[str, Any]]:
    """
    Update verification flags for user ('gov' or 'admin').
    If both gov_verified and admin_verified are True, set status='approved'.
    """
    # ponytail: minimal dual-flag toggle, upgrade to workflow state machine if audits require it
    users = load_users()
    for u in users:
        if u.get("id") == user_id:
            if verifier == "admin":
                u["admin_verified"] = True
            elif verifier == "gov":
                u["gov_verified"] = True

            if u.get("is_new_industry"):
                if u.get("admin_verified") and u.get("gov_verified"):
                    u["status"] = "approved"
            else:
                u["status"] = "approved"

            save_users(users)
            return u
    return None

def update_user_status(user_id: str, status: str) -> Optional[Dict[str, Any]]:
    """Update registration status (approved/rejected/pending) for a user."""
    users = load_users()
    for u in users:
        if u.get("id") == user_id:
            u["status"] = status
            save_users(users)
            return sanitize_user(u)
    return None

def delete_user(user_id: str) -> bool:
    """Delete a user by ID from storage."""
    users = load_users()
    filtered = [u for u in users if u.get("id") != user_id]
    if len(filtered) == len(users):
        return False
    save_users(filtered)
    return True

# --- System State & Audit Log Helpers ---

def load_system_state() -> Dict[str, Any]:
    """Load system settings, audit log, broadcast messages, and citizen grievances."""
    if not os.path.exists(STATE_PATH):
        return {
            "settings": {},
            "broadcast_message": {},
            "audit_log": [],
            "citizen_grievances": [],
            "issued_notices": [],
            "plume_overrides": {}
        }
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_system_state(state: Dict[str, Any]) -> None:
    """Safely persist system state dictionary to data/system_state.json."""
    save_json_safely(STATE_PATH, state)

def log_audit_action(user_email: str, user_name: str, role: str, action: str, details: str) -> Dict[str, Any]:
    """Append a mutating action record to system_state.json audit log."""
    state = load_system_state()
    audit_list = state.setdefault("audit_log", [])
    entry = {
        "id": f"AUD-{1000 + len(audit_list) + 1}",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_email": user_email,
        "user_name": user_name,
        "role": role,
        "action": action,
        "details": details
    }
    audit_list.insert(0, entry) # Most recent first
    if len(audit_list) > 200:
        state["audit_log"] = audit_list[:200]
    save_system_state(state)
    return entry

# --- In-Memory Session Management ---

def create_session(user: Dict[str, Any]) -> str:
    """Generate a high-entropy bearer token and store the session."""
    token = secrets.token_hex(32)
    sanitized = sanitize_user(user)
    SESSIONS[token] = {
        "user": sanitized,
        "created_at": datetime.utcnow().isoformat()
    }
    return token

def delete_session(token: str) -> bool:
    """Invalidate a bearer session token."""
    if token in SESSIONS:
        del SESSIONS[token]
        return True
    return False

def get_session_user(token: str) -> Optional[Dict[str, Any]]:
    """Retrieve user object for a given token."""
    session = SESSIONS.get(token)
    if session:
        return session.get("user")
    return None

# --- FastAPI Authentication & RBAC Dependencies ---

def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    FastAPI dependency: extracts Bearer token from 'Authorization' header or 'token' query param.
    Raises 401 Unauthorized if missing or invalid.
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    user = get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid token")

    return user

def require_roles(allowed_roles: List[str]):
    """
    FastAPI dependency factory: ensures authenticated user possesses one of the allowed roles.
    Raises 403 Forbidden if user lacks required permissions.
    """
    def role_dependency(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        role = current_user.get("role", "")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: Role '{role}' is not authorized to access this resource"
            )
        return current_user
    return role_dependency

