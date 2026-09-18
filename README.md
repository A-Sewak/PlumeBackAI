# PlumeBacktrace AI - Backend & Inverse Dispersion Engine

An automated satellite gas plume back-calculation engine designed to detect illegal off-peak chemical emissions and pinpoint culprit factory clusters.

---

## 🚀 Quick Start (In VS Code)

### Step 1: Open in VS Code
Open the `plume-backtrace-backend` folder directly in VS Code.

### Step 2: Install & Run
Double-click `run.bat` (on Windows) or run in your terminal:
```bash
pip install -r requirements.txt
python main.py
```

Open your browser to:
* **Interactive 3D Dashboard:** `http://localhost:8000`
* **Interactive API Docs (Swagger):** `http://localhost:8000/docs`

---

## 🗺️ How to Swap in ANY Locality Dataset

The backend is 100% modular. You can change the target industrial zone in two simple ways:

### Method 1: Just Replace `data/factories.geojson`
Paste your locality's factory coordinates into `data/factories.geojson`. The format is standard GeoJSON:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "FAC-01",
        "name": "Your Factory Name",
        "category": "Chemical / Tannery / Dyeing",
        "emissions": ["SO2", "NO2"],
        "prior_violations_count": 2
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[lon, lat], [lon, lat], ...]]
      }
    }
  ]
}
```

### Method 2: Use the Web UI Upload Button
Click **"Change Locality"** in the top right of the dashboard and upload any `.geojson` file directly!

---

## ⚡ API Endpoints (For Your Custom React / Next.js Frontend)

If you are building your own frontend in React/Vite, the backend has full CORS enabled out of the box!

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/factories` | Returns all factories for the active industrial zone |
| `GET` | `/api/spikes` | Returns pre-loaded satellite anomaly scenarios |
| `POST` | `/api/trace` | Computes reverse dispersion cone & ranks suspect factories |
| `POST` | `/api/notice/pdf` | Generates official statutory violation citation PDF |
| `POST` | `/api/upload-factories` | Upload a new GeoJSON dataset dynamically |

---

## 🔬 Mathematical Physics

* **Pasquill-Gifford Dispersion:** Calculates $\sigma_y(x) = a \cdot x^b$ based on nocturnal thermal inversion stability Class F.
* **Inverse Atmospheric Vector:** Traces the meteorological heading backwards from the satellite detection coordinate.
* **Gaussian Likelihood Scoring:**
  $$P_{spatial} = \exp\left(-\frac{d_{cross}^2}{2\sigma_y^2}\right)$$
* **Statutory Penalty Assessment:** Evaluates fines according to the Indian Air (Prevention and Control of Pollution) Act 1981 Section 21 and Water Act 1974 Section 24.
