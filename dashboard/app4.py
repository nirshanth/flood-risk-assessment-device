from flask import Flask, jsonify, request, redirect, session, render_template_string
import sqlite3
from datetime import datetime
import requests
import os

app = Flask(__name__)
app.secret_key = "secret123"

USERNAME = "admin"
PASSWORD = "1234"
DB_NAME = "flood_data.db"


# --------------------------------------------------
# Database helpers
# --------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            water1 INTEGER NOT NULL,
            water2 INTEGER NOT NULL,
            water3 INTEGER NOT NULL,
            water INTEGER NOT NULL,
            distance INTEGER NOT NULL,
            rain TEXT NOT NULL,
            risk TEXT NOT NULL
        )
    """)
    conn.commit()

    # Handle upgrades from your old schema
    cursor.execute("PRAGMA table_info(readings)")
    columns = [row[1] for row in cursor.fetchall()]

    if "water1" not in columns:
        cursor.execute("ALTER TABLE readings ADD COLUMN water1 INTEGER NOT NULL DEFAULT 0")
    if "water2" not in columns:
        cursor.execute("ALTER TABLE readings ADD COLUMN water2 INTEGER NOT NULL DEFAULT 0")
    if "water3" not in columns:
        cursor.execute("ALTER TABLE readings ADD COLUMN water3 INTEGER NOT NULL DEFAULT 0")

    conn.commit()
    conn.close()


def calculate_combined_water(water1: int, water2: int, water3: int) -> int:
    return min(water1, water2, water3)


def calculate_rain_status(water1: int, water2: int, water3: int) -> str:
    return "Rain Detected" if min(water1, water2, water3) < 500 else "No Rain"


def calculate_risk(water: int, distance: int) -> str:
    if water < 300 or distance < 80:
        return "High"
    elif water < 500 or distance < 150:
        return "Medium"
    return "Low"


def insert_reading(water1: int, water2: int, water3: int, distance: int):
    water = calculate_combined_water(water1, water2, water3)
    rain = calculate_rain_status(water1, water2, water3)
    risk = calculate_risk(water, distance)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO readings (timestamp, water1, water2, water3, water, distance, rain, risk)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, water1, water2, water3, water, distance, rain, risk))
    conn.commit()
    conn.close()


def get_latest_reading():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, water1, water2, water3, water, distance, rain, risk
        FROM readings
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "timestamp": row[0],
            "water1": row[1],
            "water2": row[2],
            "water3": row[3],
            "water": row[4],
            "distance": row[5],
            "rain": row[6],
            "risk": row[7]
        }

    return {
        "timestamp": "--",
        "water1": "--",
        "water2": "--",
        "water3": "--",
        "water": "--",
        "distance": "--",
        "rain": "Unknown",
        "risk": "Unknown"
    }


def get_recent_readings(limit=20):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, water1, water2, water3, water, distance, risk
        FROM readings
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    rows.reverse()
    return [
        {
            "timestamp": row[0],
            "water1": row[1],
            "water2": row[2],
            "water3": row[3],
            "water": row[4],
            "distance": row[5],
            "risk": row[6]
        }
        for row in rows
    ]


# --------------------------------------------------
# Weather helpers
# --------------------------------------------------
def geocode_location(location):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": location,
        "count": 1,
        "language": "en",
        "format": "json"
    }

    response = requests.get(url, params=params, timeout=8)
    response.raise_for_status()
    data = response.json()

    results = data.get("results")
    if not results:
        return None

    result = results[0]

    parts = [result.get("name")]
    if result.get("admin1"):
        parts.append(result["admin1"])
    if result.get("country"):
        parts.append(result["country"])

    display_name = ", ".join([p for p in parts if p])

    return {
        "name": display_name,
        "latitude": result["latitude"],
        "longitude": result["longitude"]
    }


def weather_label_from_code(code):
    if code is None:
        return "Unknown"
    if code == 0:
        return "Clear"
    if code in [1, 2, 3]:
        return "Partly Cloudy"
    if code in [45, 48]:
        return "Fog"
    if code in [51, 53, 55, 56, 57]:
        return "Drizzle"
    if code in [61, 63, 65, 66, 67, 80, 81, 82]:
        return "Rain"
    if code in [71, 73, 75, 77, 85, 86]:
        return "Snow"
    if code in [95, 96, 99]:
        return "Thunderstorm"
    return "Mixed"


def get_weather_bundle(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "precipitation",
            "rain",
            "weather_code",
            "wind_speed_10m"
        ]),
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max"
        ]),
        "forecast_days": 7,
        "timezone": "auto",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch"
    }

    response = requests.get(url, params=params, timeout=8)
    response.raise_for_status()
    data = response.json()

    current = data.get("current", {})
    daily = data.get("daily", {})

    forecast = []
    dates = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    rain = daily.get("precipitation_sum", [])
    rain_prob = daily.get("precipitation_probability_max", [])
    weather_codes = daily.get("weather_code", [])

    for i in range(len(dates)):
        code = weather_codes[i] if i < len(weather_codes) else None
        forecast.append({
            "date": dates[i],
            "summary": weather_label_from_code(code),
            "max_temp": max_temps[i] if i < len(max_temps) else None,
            "min_temp": min_temps[i] if i < len(min_temps) else None,
            "rain_in": rain[i] if i < len(rain) else 0,
            "rain_probability": rain_prob[i] if i < len(rain_prob) else 0,
            "weather_code": code
        })

    current_code = current.get("weather_code")

    return {
        "current": {
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "precipitation": current.get("precipitation"),
            "rain": current.get("rain"),
            "wind_speed": current.get("wind_speed_10m"),
            "summary": weather_label_from_code(current_code)
        },
        "forecast": forecast
    }


def calculate_combined_risk(sensor_data, weather_data):
    sensor_risk = sensor_data.get("risk", "Unknown")
    forecast = weather_data.get("forecast", [])

    next_24h = forecast[:2]

    max_rain_probability = 0
    total_rain_in = 0

    for day in next_24h:
        rain_prob = day.get("rain_probability") or 0
        rain_in = day.get("rain_in") or 0
        max_rain_probability = max(max_rain_probability, rain_prob)
        total_rain_in += rain_in

    if sensor_risk == "High":
        return {
            "level": "High",
            "message": "High flood risk from live sensor readings.",
            "source": "sensor"
        }

    if sensor_risk == "Medium" and (max_rain_probability >= 70 or total_rain_in >= 1.0):
        return {
            "level": "High",
            "message": "Sensor conditions are elevated and heavy rain is likely soon.",
            "source": "sensor+weather"
        }

    if sensor_risk == "Low" and (max_rain_probability >= 80 or total_rain_in >= 1.2):
        return {
            "level": "Medium",
            "message": "Sensor normal, but weather risk is elevated.",
            "source": "weather"
        }

    if max_rain_probability >= 70 or total_rain_in >= 0.75:
        return {
            "level": "Medium",
            "message": "Heavy rain likely in the next 24 hours.",
            "source": "weather"
        }

    if sensor_risk == "Medium":
        return {
            "level": "Medium",
            "message": "Moderate flood risk from current live sensor readings.",
            "source": "sensor"
        }

    return {
        "level": "Low",
        "message": "Low current flood likelihood.",
        "source": "combined"
    }


# --------------------------------------------------
# HTML templates
# --------------------------------------------------
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Flood Monitoring Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: Arial, sans-serif;
            background:
                radial-gradient(circle at top left, rgba(59,130,246,0.22), transparent 28%),
                radial-gradient(circle at bottom right, rgba(16,185,129,0.18), transparent 25%),
                linear-gradient(135deg, #0b1220, #111827 55%, #0f172a);
            color: white;
        }
        .login-box {
            width: 100%;
            max-width: 390px;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.08);
            backdrop-filter: blur(14px);
            padding: 30px;
            border-radius: 22px;
            box-shadow: 0 18px 50px rgba(0,0,0,0.35);
        }
        h2 {
            margin-top: 0;
            text-align: center;
            margin-bottom: 8px;
        }
        .sub {
            text-align: center;
            color: #cbd5e1;
            margin-bottom: 22px;
            font-size: 14px;
        }
        input {
            width: 100%;
            padding: 14px;
            margin-bottom: 14px;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            outline: none;
            font-size: 15px;
            background: rgba(255,255,255,0.08);
            color: white;
        }
        input::placeholder { color: #cbd5e1; }
        button {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 12px;
            background: linear-gradient(90deg, #2563eb, #06b6d4);
            color: white;
            font-size: 15px;
            font-weight: bold;
            cursor: pointer;
        }
        .error {
            color: #fecaca;
            text-align: center;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>Flood Monitoring Login</h2>
        <div class="sub">Secure access to your sensor dashboard</div>
        <form method="post">
            <input name="username" placeholder="Username" required>
            <input name="password" type="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Flood Monitoring Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

    <link
      rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
      crossorigin=""
    />
    <script
      src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
      integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
      crossorigin=""
    ></script>

    <style>
        * { box-sizing: border-box; }

        :root {
            --bg1: #08111f;
            --bg2: #0f172a;
            --bg3: #111827;
            --glass: rgba(255,255,255,0.08);
            --glass-2: rgba(255,255,255,0.05);
            --border: rgba(255,255,255,0.08);
            --text-soft: #cbd5e1;
            --text-muted: #94a3b8;
            --blue: #38bdf8;
            --cyan: #06b6d4;
            --green: #22c55e;
            --amber: #f59e0b;
            --red: #ef4444;
        }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            color: white;
            background:
                radial-gradient(circle at top left, rgba(56,189,248,0.16), transparent 26%),
                radial-gradient(circle at bottom right, rgba(34,197,94,0.12), transparent 24%),
                linear-gradient(135deg, var(--bg1), var(--bg3) 50%, var(--bg2));
            min-height: 100vh;
        }

        .navbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 18px 28px;
            background: rgba(255,255,255,0.05);
            border-bottom: 1px solid var(--border);
            backdrop-filter: blur(14px);
            position: sticky;
            top: 0;
            z-index: 30;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-badge {
            width: 42px;
            height: 42px;
            border-radius: 14px;
            background: linear-gradient(135deg, #2563eb, #06b6d4);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            box-shadow: 0 10px 30px rgba(37,99,235,0.28);
        }

        .brand h1 {
            margin: 0;
            font-size: 24px;
        }

        .brand p {
            margin: 2px 0 0;
            color: var(--text-muted);
            font-size: 13px;
        }

        .logout-btn {
            text-decoration: none;
            background: rgba(239,68,68,0.18);
            border: 1px solid rgba(239,68,68,0.25);
            color: white;
            padding: 10px 15px;
            border-radius: 12px;
            font-weight: bold;
        }

        .container {
            max-width: 1300px;
            margin: 26px auto;
            padding: 0 18px 40px;
        }

        .hero {
            display: grid;
            grid-template-columns: 1.4fr 0.9fr;
            gap: 18px;
            margin-bottom: 22px;
        }

        .hero-card, .status-card, .panel, .forecast-card {
            background: var(--glass);
            border: 1px solid var(--border);
            border-radius: 22px;
            box-shadow: 0 16px 40px rgba(0,0,0,0.22);
            backdrop-filter: blur(14px);
        }

        .hero-card {
            padding: 24px;
        }

        .hero-title {
            font-size: 30px;
            font-weight: 700;
            margin-bottom: 8px;
        }

        .hero-sub {
            color: var(--text-soft);
            line-height: 1.5;
            max-width: 760px;
        }

        .hero-tags {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 18px;
        }

        .pill {
            padding: 10px 14px;
            border-radius: 999px;
            background: rgba(255,255,255,0.06);
            border: 1px solid var(--border);
            font-size: 13px;
            color: var(--text-soft);
        }

        .status-card {
            padding: 24px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        .status-label {
            font-size: 14px;
            color: var(--text-soft);
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .status-value {
            font-size: 40px;
            font-weight: 800;
            margin-bottom: 8px;
        }

        .risk-low { color: var(--green); }
        .risk-medium { color: var(--amber); }
        .risk-high { color: var(--red); }

        .tab-row {
            display: flex;
            gap: 10px;
            margin-bottom: 18px;
            flex-wrap: wrap;
        }

        .tab-btn {
            border: 1px solid var(--border);
            background: rgba(255,255,255,0.04);
            color: white;
            padding: 12px 18px;
            border-radius: 14px;
            cursor: pointer;
            font-weight: 700;
        }

        .tab-btn.active {
            background: linear-gradient(90deg, #2563eb, #06b6d4);
            border-color: transparent;
        }

        .tab-panel {
            display: none;
        }

        .tab-panel.active {
            display: block;
        }

        .cards-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 16px;
            margin-bottom: 18px;
        }

        .panel {
            padding: 20px;
        }

        .card-title {
            font-size: 13px;
            color: var(--text-soft);
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .card-value {
            font-size: 30px;
            font-weight: 800;
        }

        .card-foot {
            margin-top: 8px;
            color: var(--text-muted);
            font-size: 13px;
        }

        .chart-panel {
            padding: 20px;
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: end;
            gap: 16px;
            margin-bottom: 18px;
            flex-wrap: wrap;
        }

        .panel-header h2 {
            margin: 0 0 6px;
        }

        .panel-header p {
            margin: 0;
            color: var(--text-soft);
        }

        canvas {
            background: rgba(255,255,255,0.95);
            border-radius: 16px;
            padding: 8px;
        }

        .weather-top {
            display: grid;
            grid-template-columns: 1.1fr 0.9fr;
            gap: 18px;
            margin-bottom: 18px;
        }

        .search-box {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin: 14px 0 18px;
        }

        .search-box input {
            flex: 1;
            min-width: 220px;
            padding: 14px;
            border-radius: 14px;
            border: 1px solid var(--border);
            background: rgba(255,255,255,0.06);
            color: white;
            outline: none;
        }

        .search-box input::placeholder {
            color: var(--text-soft);
        }

        .search-box button {
            padding: 14px 18px;
            border-radius: 14px;
            border: none;
            background: linear-gradient(90deg, #2563eb, #06b6d4);
            color: white;
            font-weight: 700;
            cursor: pointer;
        }

        .current-weather-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin-top: 16px;
        }

        .mini {
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 16px;
        }

        .mini .label {
            font-size: 12px;
            color: var(--text-soft);
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .mini .value {
            font-size: 24px;
            font-weight: 800;
        }

        #map {
            height: 420px;
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid var(--border);
        }

        .forecast-grid {
            display: grid;
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 14px;
            margin-top: 18px;
        }

        .forecast-card {
            padding: 16px;
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            border-radius: 18px;
        }

        .forecast-date {
            font-weight: 800;
            margin-bottom: 10px;
        }

        .forecast-line {
            color: var(--text-soft);
            font-size: 14px;
            margin-bottom: 6px;
        }

        .muted {
            color: var(--text-muted);
        }

        .error-text {
            color: #fecaca;
            margin-top: 8px;
        }

        @media (max-width: 1100px) {
            .hero,
            .weather-top {
                grid-template-columns: 1fr;
            }

            .cards-grid,
            .current-weather-grid,
            .forecast-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 700px) {
            .cards-grid,
            .current-weather-grid,
            .forecast-grid {
                grid-template-columns: 1fr;
            }

            .brand h1 {
                font-size: 20px;
            }

            .hero-title {
                font-size: 24px;
            }

            .status-value,
            .card-value {
                font-size: 26px;
            }
        }
    </style>
</head>
<body>
    <div class="navbar">
        <div class="brand">
            <div class="brand-badge">FR</div>
            <div>
                <h1>Flood Risk Intelligence</h1>
                <p>Live device telemetry and weather awareness</p>
            </div>
        </div>
        <a class="logout-btn" href="/logout">Logout</a>
    </div>

    <div class="container">
        <div class="hero">
            <div class="hero-card">
                <div class="hero-title">Smart Flood Monitoring Dashboard</div>
                <div class="hero-sub">
                    Monitor your Raspberry Pi + Arduino flood device in real time, store historical readings,
                    and compare local conditions with forecast-based weather signals from any searched location.
                </div>
                <div class="hero-tags">
                    <div class="pill">Live Sensor Stream</div>
                    <div class="pill">Stored History</div>
                    <div class="pill">Interactive Weather Map</div>
                    <div class="pill">7-Day Forecast</div>
                </div>
            </div>

            <div class="status-card">
                <div class="status-label">Current Device Risk</div>
                <div class="status-value" id="heroRisk">--</div>
                <div class="muted">Latest device update: <span id="timestamp">--</span></div>
            </div>
        </div>

        <div class="tab-row">
            <button class="tab-btn active" onclick="switchTab('floodTab', this)">Flood Monitoring</button>
            <button class="tab-btn" onclick="switchTab('weatherTab', this)">Weather</button>
        </div>

        <div id="floodTab" class="tab-panel active">
            <div class="cards-grid">
                <div class="panel">
                    <div class="card-title">Water Sensor</div>
                    <div class="card-value" id="water">--</div>
                    <div class="card-foot">Lowest reading across 3 sensors</div>
                </div>

                <div class="panel">
                    <div class="card-title">Distance</div>
                    <div class="card-value" id="distance">-- mm</div>
                    <div class="card-foot">Measured water distance</div>
                </div>

                <div class="panel">
                    <div class="card-title">Rain Status</div>
                    <div class="card-value" id="rain">--</div>
                    <div class="card-foot">Rain detected if any of 3 sensors are wet</div>
                </div>

                <div class="panel">
                    <div class="card-title">Risk Level</div>
                    <div class="card-value" id="risk">--</div>
                    <div class="card-foot">Current flood risk from device data</div>
                </div>
            </div>

            <div class="panel chart-panel">
                <div class="panel-header">
                    <div>
                        <h2>Live Sensor History</h2>
                        <p>Water and distance values update automatically every 2 seconds.</p>
                    </div>
                    <div class="muted">Stored in SQLite</div>
                </div>
                <canvas id="sensorChart" height="110"></canvas>
            </div>
        </div>

        <div id="weatherTab" class="tab-panel">
            <div class="weather-top">
                <div class="panel">
                    <div class="panel-header">
                        <div>
                            <h2>Weather Search</h2>
                            <p>Enter a city, town, or ZIP code to view the forecast, map, and combined flood warning.</p>
                        </div>
                    </div>

                    <div class="search-box">
                        <input type="text" id="locationInput" placeholder="Example: New Brunswick, NJ or 08854">
                        <button onclick="loadWeather()">Get Weather</button>
                    </div>

                    <div class="muted">Forecast location: <span id="weatherLocation">None selected</span></div>
                    <div id="weatherError" class="error-text"></div>

                    <div class="mini" style="margin-top:16px; margin-bottom:16px;">
                        <div class="label">Combined Risk Engine</div>
                        <div class="value" id="combinedRiskLevel">--</div>
                        <div class="muted" id="combinedRiskMessage">No analysis yet.</div>
                    </div>

                    <div class="current-weather-grid">
                        <div class="mini">
                            <div class="label">Current Temp</div>
                            <div class="value" id="currentTemp">-- °F</div>
                        </div>
                        <div class="mini">
                            <div class="label">Feels Like</div>
                            <div class="value" id="feelsLike">-- °F</div>
                        </div>
                        <div class="mini">
                            <div class="label">Condition</div>
                            <div class="value" id="weatherSummary">--</div>
                        </div>
                        <div class="mini">
                            <div class="label">Wind</div>
                            <div class="value" id="windSpeed">-- mph</div>
                        </div>
                    </div>

                    <div class="current-weather-grid">
                        <div class="mini">
                            <div class="label">Precipitation</div>
                            <div class="value" id="precipitationNow">-- in</div>
                        </div>
                        <div class="mini">
                            <div class="label">Rain</div>
                            <div class="value" id="rainNow">-- in</div>
                        </div>
                    </div>
                </div>

                <div class="panel">
                    <div class="panel-header">
                        <div>
                            <h2>Location Map</h2>
                            <p>Marker updates to the searched forecast location.</p>
                        </div>
                    </div>
                    <div id="map"></div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div>
                        <h2>7-Day Forecast</h2>
                        <p>Forecast temperatures are shown in Fahrenheit.</p>
                    </div>
                </div>
                <div id="forecastContainer" class="forecast-grid"></div>
            </div>
        </div>
    </div>

    <script>
        let sensorChart;
        let map;
        let marker;

        function initMap() {
            map = L.map('map').setView([40.4862, -74.4518], 10);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(map);

            marker = L.marker([40.4862, -74.4518]).addTo(map)
                .bindPopup('Default map location')
                .openPopup();
        }

        function switchTab(tabId, btn) {
            document.querySelectorAll('.tab-panel').forEach(panel => {
                panel.classList.remove('active');
            });

            document.querySelectorAll('.tab-btn').forEach(button => {
                button.classList.remove('active');
            });

            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');

            if (tabId === 'weatherTab' && map) {
                setTimeout(() => map.invalidateSize(), 150);
            }
        }

        async function loadChartData() {
            const response = await fetch('/history');
            const history = await response.json();

            const labels = history.map(item => item.timestamp.split(' ')[1]);
            const waterData = history.map(item => item.water);
            const distanceData = history.map(item => item.distance);

            const ctx = document.getElementById('sensorChart').getContext('2d');

            if (sensorChart) {
                sensorChart.data.labels = labels;
                sensorChart.data.datasets[0].data = waterData;
                sensorChart.data.datasets[1].data = distanceData;
                sensorChart.update();
            } else {
                sensorChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Water Sensor',
                                data: waterData,
                                borderWidth: 2,
                                tension: 0.32
                            },
                            {
                                label: 'Distance (mm)',
                                data: distanceData,
                                borderWidth: 2,
                                tension: 0.32
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true
                    }
                });
            }
        }

        async function loadLatestData() {
            const response = await fetch('/data');
            const data = await response.json();

            document.getElementById('water').textContent = data.water;
            document.getElementById('distance').textContent = data.distance + ' mm';
            document.getElementById('rain').textContent = data.rain;

            const riskElement = document.getElementById('risk');
            const heroRiskElement = document.getElementById('heroRisk');

            riskElement.textContent = data.risk;
            heroRiskElement.textContent = data.risk;

            riskElement.className = 'card-value';
            heroRiskElement.className = 'status-value';

            if (data.risk === 'Low') {
                riskElement.classList.add('risk-low');
                heroRiskElement.classList.add('risk-low');
            } else if (data.risk === 'Medium') {
                riskElement.classList.add('risk-medium');
                heroRiskElement.classList.add('risk-medium');
            } else if (data.risk === 'High') {
                riskElement.classList.add('risk-high');
                heroRiskElement.classList.add('risk-high');
            }

            document.getElementById('timestamp').textContent = data.timestamp;
        }

        async function refreshDashboard() {
            await loadLatestData();
            await loadChartData();
        }

        function formatDate(dateString) {
            const date = new Date(dateString + "T00:00:00");
            return date.toLocaleDateString([], {
                weekday: 'short',
                month: 'short',
                day: 'numeric'
            });
        }

        function updateMap(lat, lon, label) {
            if (!map) return;

            map.setView([lat, lon], 11);
            marker.setLatLng([lat, lon]);
            marker.bindPopup(label).openPopup();
        }

        async function loadWeather() {
            const location = document.getElementById('locationInput').value.trim();
            const container = document.getElementById('forecastContainer');
            const errorBox = document.getElementById('weatherError');

            container.innerHTML = "";
            errorBox.textContent = "";

            if (!location) {
                errorBox.textContent = "Please enter a location.";
                return;
            }

            try {
                const response = await fetch(`/combined-risk?location=${encodeURIComponent(location)}`);
                const data = await response.json();

                if (!response.ok) {
                    errorBox.textContent = data.error || "Unable to load weather.";
                    return;
                }

                document.getElementById('weatherLocation').textContent = data.location.name;
                document.getElementById('currentTemp').textContent = `${data.current_weather.temperature} °F`;
                document.getElementById('feelsLike').textContent = `${data.current_weather.feels_like} °F`;
                document.getElementById('weatherSummary').textContent = data.current_weather.summary;
                document.getElementById('windSpeed').textContent = `${data.current_weather.wind_speed} mph`;
                document.getElementById('precipitationNow').textContent = `${data.current_weather.precipitation} in`;
                document.getElementById('rainNow').textContent = `${data.current_weather.rain} in`;

                const combinedRiskLevel = document.getElementById('combinedRiskLevel');
                const combinedRiskMessage = document.getElementById('combinedRiskMessage');

                combinedRiskLevel.textContent = data.combined_risk.level;
                combinedRiskMessage.textContent = data.combined_risk.message;

                combinedRiskLevel.className = 'value';
                if (data.combined_risk.level === 'Low') {
                    combinedRiskLevel.classList.add('risk-low');
                } else if (data.combined_risk.level === 'Medium') {
                    combinedRiskLevel.classList.add('risk-medium');
                } else if (data.combined_risk.level === 'High') {
                    combinedRiskLevel.classList.add('risk-high');
                }

                updateMap(data.location.latitude, data.location.longitude, data.location.name);

                data.forecast.forEach(day => {
                    const card = document.createElement('div');
                    card.className = 'forecast-card';
                    card.innerHTML = `
                        <div class="forecast-date">${formatDate(day.date)}</div>
                        <div class="forecast-line"><strong>${day.summary}</strong></div>
                        <div class="forecast-line">High: ${day.max_temp} °F</div>
                        <div class="forecast-line">Low: ${day.min_temp} °F</div>
                        <div class="forecast-line">Rain: ${day.rain_in} in</div>
                        <div class="forecast-line">Rain chance: ${day.rain_probability}%</div>
                    `;
                    container.appendChild(card);
                });

                localStorage.setItem("saved_weather_location", location);
            } catch (error) {
                errorBox.textContent = "Error loading weather data.";
                console.log(error);
            }
        }

        function restoreSavedLocation() {
            const saved = localStorage.getItem("saved_weather_location");
            if (saved) {
                document.getElementById("locationInput").value = saved;
                loadWeather();
            }
        }

        initMap();
        refreshDashboard();
        setInterval(refreshDashboard, 2000);
        restoreSavedLocation();
    </script>
</body>
</html>
"""


# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.route("/")
def root():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password")

        if user == USERNAME and pwd == PASSWORD:
            session["logged_in"] = True
            return redirect("/dashboard")
        else:
            error = "Invalid login"

    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/login")


@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect("/login")
    return render_template_string(DASHBOARD_HTML)


@app.route("/data")
def data():
    if not session.get("logged_in"):
        return redirect("/login")
    return jsonify(get_latest_reading())


@app.route("/history")
def history():
    if not session.get("logged_in"):
        return redirect("/login")
    return jsonify(get_recent_readings(20))


@app.route("/update", methods=["POST"])
def update():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data received"}), 400

    try:
        water1 = int(data["water1"])
        water2 = int(data["water2"])
        water3 = int(data["water3"])
        distance = int(data["distance"])

        insert_reading(water1, water2, water3, distance)
        return jsonify({"message": "Reading stored successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/weather-bundle")
def weather_bundle():
    if not session.get("logged_in"):
        return redirect("/login")

    location = request.args.get("location", "").strip()
    if not location:
        return jsonify({"error": "Location is required"}), 400

    try:
        geo = geocode_location(location)
        if not geo:
            return jsonify({"error": "Location not found"}), 404

        weather = get_weather_bundle(geo["latitude"], geo["longitude"])

        return jsonify({
            "location": geo,
            "current": weather["current"],
            "forecast": weather["forecast"]
        })
    except Exception as e:
        return jsonify({"error": f"Weather lookup failed: {str(e)}"}), 500


@app.route("/combined-risk")
def combined_risk():
    if not session.get("logged_in"):
        return redirect("/login")

    location = request.args.get("location", "").strip()
    if not location:
        return jsonify({"error": "Location is required"}), 400

    try:
        geo = geocode_location(location)
        if not geo:
            return jsonify({"error": "Location not found"}), 404

        weather = get_weather_bundle(geo["latitude"], geo["longitude"])
        sensor = get_latest_reading()
        combined = calculate_combined_risk(sensor, weather)

        return jsonify({
            "location": geo,
            "sensor": sensor,
            "current_weather": weather["current"],
            "forecast": weather["forecast"],
            "combined_risk": combined
        })
    except Exception as e:
        return jsonify({"error": f"Combined risk lookup failed: {str(e)}"}), 500


# --------------------------------------------------
# Start app
# --------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
