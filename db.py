"""
PlumeBacktrace AI - Nocturnal Violations Database (10 PM - 6 AM Curfew)
Zero-dependency SQLite storage using Python stdlib.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "violations.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create night_violations table if it does not exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS night_violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factory_id TEXT NOT NULL,
                factory_name TEXT NOT NULL,
                registration_no TEXT,
                pollutant TEXT NOT NULL,
                concentration REAL NOT NULL,
                confidence_score REAL NOT NULL,
                detection_timestamp TEXT NOT NULL,
                est_release_time TEXT,
                penalty_inr INTEGER NOT NULL,
                plume_lat REAL NOT NULL,
                plume_lon REAL NOT NULL,
                source TEXT DEFAULT 'satellite',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def is_curfew_hours(dt_str: Optional[str] = None) -> bool:
    """Continuous 24/7 surveillance: active all the time."""
    return True

def record_night_violation(
    factory: Dict[str, Any],
    pollutant: str,
    concentration: float,
    plume_lat: float,
    plume_lon: float,
    detection_timestamp: str,
    source: str = "satellite"
) -> Optional[int]:
    """Store violation into database across all hours (24/7 continuous logging)."""
    init_db()
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO night_violations (
                factory_id, factory_name, registration_no, pollutant,
                concentration, confidence_score, detection_timestamp,
                est_release_time, penalty_inr, plume_lat, plume_lon, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            factory.get("factory_id", "UNKNOWN"),
            factory.get("name", "Unknown Unit"),
            factory.get("registration_no", "N/A"),
            pollutant,
            float(concentration),
            float(factory.get("confidence_score", 0.0)),
            detection_timestamp,
            factory.get("est_release_time", "N/A"),
            int(factory.get("calculated_fine_inr", 1500000)),
            float(plume_lat),
            float(plume_lon),
            source
        ))
        conn.commit()
        return cursor.lastrowid

def get_all_night_violations() -> List[Dict[str, Any]]:
    """Retrieve all logged 10 PM - 6 AM violations."""
    init_db()
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM night_violations ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

def clear_violations():
    init_db()
    with get_db() as conn:
        conn.execute("DELETE FROM night_violations")
        conn.commit()

