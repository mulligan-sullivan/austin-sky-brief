#!/usr/bin/env python3
"""
Austin Sky + Weather Daily Brief
Pushes to ntfy. Runs via GitHub Actions.
"""

import os
import sys
import math
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from skyfield.api import Loader, wgs84
from skyfield import almanac

# ==================== CONFIG ====================
LAT = 30.2672
LON = -97.7431
ELEVATION_M = 149
TZ = ZoneInfo("America/Chicago")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

# Minimum altitude to report as "meaningfully up."
ALTITUDE_THRESHOLD = 15  # degrees

# Temperature scale: 46.4°F = 0%, 88.3°F = 100%
DAY_TEMP_MIN = 46.4
DAY_TEMP_MAX = 88.3

# Rain scale: 0 inches = 0%, 0.653 inches = 100%
RAIN_MAX = 0.653

# Wind scale: 2.64 mph = 0%, 18.37 mph = 100%
WIND_MIN = 2.64
WIND_MAX = 18.37

# ==================== SKYFIELD SETUP ====================
load = Loader('./skyfield_data')
eph = load('de421.bsp')
ts = load.timescale()

sun = eph['sun']
moon = eph['moon']
earth = eph['earth']
austin = wgs84.latlon(LAT, LON, elevation_m=ELEVATION_M)
observer = earth + austin

PLANETS = {
    'Mercury': eph['mercury'],
    'Venus': eph['venus'],
    'Mars': eph['mars'],
    'Jupiter': eph['jupiter barycenter'],
    'Saturn': eph['saturn barycenter'],
    'Uranus': eph['uranus barycenter'],
    'Neptune': eph['neptune barycenter'],
}

# ==================== HELPERS ====================

def make_austin_dt(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)

def sun_elevation_degrees(dt):
    t = ts.from_datetime(dt)
    apparent = observer.at(t).observe(sun).apparent()
    alt, az, dist = apparent.altaz()
    return alt.degrees

def twilight_category(elev):
    if elev > -0.833:
        return "Daylight"
    elif elev > -6:
        return "Civil twilight"
    elif elev > -12:
        return "Nautical twilight"
    elif elev > -18:
        return "Astronomical twilight"
    else:
        return "Night"

def twilight_percent(elev, category):
    if category == "Civil twilight":
        return min(100, max(0, (elev + 6) / 5.167 * 100))
    elif category == "Nautical twilight":
        return min(100, max(0, (elev + 12) / 6 * 100))
    elif category == "Astronomical twilight":
        return min(100, max(0, (elev + 18) / 6 * 100))
    return None

def twilight_line(elev):
    cat = twilight_category(elev)
    if cat == "Night":
        below = abs(elev) - 18
        return f"night — Sun center approximately {elev:.2f}° ({below:.2f}° below −18°)"
    elif cat == "Daylight":
        return f"daylight — Sun center approximately {elev:.2f}°"
    else:
        pct = twilight_percent(elev, cat)
        return f"{cat.lower()}, about {pct:.1f}% — Sun center approximately {elev:.2f}°"

def twilight_interval_for_time(target_dt):
    """Return (start, end, category_name) for the twilight interval containing target_dt."""
    noon_prev = datetime(target_dt.year, target_dt.month, target_dt.day, 12, 0, tzinfo=TZ) - timedelta(days=1)
    noon_next = datetime(target_dt.year, target_dt.month, target_dt.day, 12, 0, tzinfo=TZ) + timedelta(days=1)
    
    t0 = ts.from_datetime(noon_prev)
    t1 = ts.from_datetime(noon_next)
    
    f = almanac.dark_twilight_day(eph, austin)
    times, events = almanac.find_discrete(t0, t1, f)
    
    phase_at_start = int(f(t0))
    
    category_names = {
        0: "Night",
        1: "Astronomical twilight",
        2: "Nautical twilight",
        3: "Civil twilight",
        4: "Daylight",
    }
    
    intervals = []
    current_start = t0.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    current_phase = phase_at_start
    
    for ti, event in zip(times, events):
        dt_local = ti.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
        intervals.append((current_start, dt_local, category_names[current_phase]))
        current_start = dt_local
        current_phase = int(event)
    
    end_search = t1.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    intervals.append((current_start, end_search, category_names[current_phase]))
    
    for start, end, cat in intervals:
        if start <= target_dt < end:
            return start, end, cat
    
    return None, None, "Unknown"

def generate_twilight_chart(date_dt, target_dt, filename):
    """Generate a 2-hour twilight timeline chart centered on target_dt."""
    window_start = target_dt - timedelta(hours=1)
    window_end = target_dt + timedelta(hours=1)
    
    t0 = ts.from_datetime(window_start - timedelta(hours=3))
    t1 = ts.from_datetime(window_end + timedelta(hours=3))
    
    f = almanac.dark_twilight_day(eph, austin)
    times, events = almanac.find_discrete(t0, t1, f)
    
    category_names = {
        0: "Night",
        1: "Astronomical twilight",
        2: "Nautical twilight",
        3: "Civil twilight",
        4: "Daylight",
    }
    
    colors = {
        "Night": "#0a1519",
        "Astronomical twilight": "#1a3a4a",
        "Nautical twilight": "#2d5a6b",
        "Civil twilight": "#5ab4d4",
        "Daylight": "#a8d8e8",
    }
    
    intervals = []
    current_start = t0.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    current_phase = int(f(t0))
    
    for ti, event in zip(times, events):
        dt_local = ti.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
        intervals.append((current_start, dt_local, category_names[current_phase]))
        current_start = dt_local
        current_phase = int(event)
    
    end_search = t1.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    intervals.append((current_start, end_search, category_names[current_phase]))
    
    fig, ax = plt.subplots(figsize=(6, 1.0), dpi=150)
    
    total_seconds = (window_end - window_start).total_seconds()
    
    for start, end, cat in intervals:
        s = max(start, window_start)
        e = min(end, window_end)
        if s >= e:
            continue
        
        left = (s - window_start).total_seconds() / total_seconds
        width = (e - s).total_seconds() / total_seconds
        
        rect = patches.FancyBboxPatch(
            (left, 0.35), width, 0.3,
            boxstyle="round,pad=0.005",
            facecolor=colors[cat], edgecolor='none'
        )
        ax.add_patch(rect)
        
        if width > 0.10:
            text_color = 'white' if cat in ['Night', 'Astronomical twilight', 'Nautical twilight'] else '#1a3a4a'
            short_name = cat.replace(' twilight', '').replace('Astronomical', 'Astro')
            ax.text(left + width/2, 0.5, short_name,
                   ha='center', va='center', fontsize=6, color=text_color, fontweight='bold')
    
    # 6:15 AM marker — solid black line
    target_left = (target_dt - window_start).total_seconds() / total_seconds
    ax.axvline(x=target_left, color='black', linewidth=2.5, linestyle='-', zorder=5)
    
    # Time labels every 30 minutes
    tick_times = []
    t = window_start
    while t <= window_end:
        tick_times.append(t)
        t += timedelta(minutes=30)
    
    tick_positions = [(t - window_start).total_seconds() / total_seconds for t in tick_times]
    tick_labels = [t.strftime('%-I:%M') for t in tick_times]
    
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=7, color='#888888')
    ax.tick_params(axis='x', length=0, pad=2)
    
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    
    plt.tight_layout(pad=0.3)
    plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none', pad_inches=0.05)
    plt.close()

def get_moon_info(dt):
    t = ts.from_datetime(dt)
    phase = almanac.moon_phase(eph, t)
    pa = phase.degrees  # 0=new, 180=full, 360=new

    illumination = (1 - math.cos(math.radians(pa))) / 2 * 100

    if pa < 180:
        trend = "Waxing"
    else:
        trend = "Waning"

    if pa < 90 or pa > 270:
        name = "crescent"
    elif pa == 180:
        name = "full"
    else:
        name = "gibbous"

    if name == "full":
        return f"Full moon, about {illumination:.0f}% illuminated"
    return f"{trend.lower()} {name}, about {illumination:.0f}% illuminated"

def planet_position(planet, dt):
    """Return (altitude_deg, azimuth_deg) for planet at dt."""
    t = ts.from_datetime(dt)
    apparent = observer.at(t).observe(planet).apparent()
    alt, az, dist = apparent.altaz()
    return alt.degrees, az.degrees

def format_alt_dir(alt, az):
    """Format altitude and azimuth as 'X° above East/West' or 'straight up'."""
    if alt >= 89:
        return "straight up"
    direction = "East" if az < 180 else "West"
    return f"{alt:.0f}° above {direction}"

def wind_direction(deg):
    """Convert wind direction degrees to cardinal."""
    dirs = ["North", "Northeast", "East", "Southeast", "South", "Southwest", "West", "Northwest"]
    idx = round(deg / 45) % 8
    return dirs[idx]

def find_next_moonrise(start_dt):
    """Find next moonrise after start_dt."""
    t0 = ts.from_datetime(start_dt)
    t1 = ts.from_datetime(start_dt + timedelta(days=2))
    
    f = almanac.risings_and_settings(eph, moon, austin)
    times, events = almanac.find_discrete(t0, t1, f)
    
    for ti, event in zip(times, events):
        if event == 1:  # 1 = rising
            dt_local = ti.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
            if dt_local > start_dt:
                return dt_local
    return None

def find_proper_night_bounds(date_dt):
    """
    Return (night_start, night_end) for proper night.
    Proper night = Sun center below -18° (outside all twilights).
    night_start = evening transition into Night.
    night_end   = morning transition out of Night.
    """
    noon = datetime(date_dt.year, date_dt.month, date_dt.day, 12, 0, tzinfo=TZ)
    t0 = ts.from_datetime(noon)
    t1 = ts.from_datetime(noon + timedelta(days=1))
    
    f = almanac.dark_twilight_day(eph, austin)
    times, events = almanac.find_discrete(t0, t1, f)
    
    night_start = None
    night_end = None
    
    for ti, event in zip(times, events):
        dt_local = ti.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
        if event == 0 and night_start is None:
            # Entering Night (end of evening astronomical twilight)
            night_start = dt_local
        elif event == 1 and night_start is not None and night_end is None:
            # Leaving Night (start of morning astronomical twilight)
            night_end = dt_local
    
    return night_start, night_end

def find_first_threshold(planet, start_dt, end_dt, threshold):
    if start_dt is None or end_dt is None or start_dt >= end_dt:
        return None
    current = start_dt
    step = timedelta(minutes=2)
    while current <= end_dt:
        alt, az = planet_position(planet, current)
        if alt >= threshold:
            return current
        current += step
    return None

def find_drop_below_threshold(planet, start_dt, end_dt, threshold):
    """Find when planet first drops below threshold after start_dt."""
    if start_dt is None or end_dt is None or start_dt >= end_dt:
        return None
    current = start_dt
    step = timedelta(minutes=2)
    while current <= end_dt:
        alt, az = planet_position(planet, current)
        if alt < threshold:
            return current
        current += step
    return None

def find_set_time(planet, start_dt, end_dt):
    """Find when planet first drops below horizon (alt < 0) after start_dt."""
    if start_dt is None or end_dt is None or start_dt >= end_dt:
        return None
    current = start_dt
    step = timedelta(minutes=2)
    while current <= end_dt:
        alt, az = planet_position(planet, current)
        if alt < 0:
            return current
        current += step
    return None

def format_time(dt):
    hour = dt.hour
    minute = dt.minute
    ampm = "am" if hour < 12 else "pm"
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
    return f"{hour_12}:{minute:02d} {ampm}"

def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=30.2672&longitude=-97.7431"
        "&current=temperature_2m,wind_speed_10m,wind_direction_10m"
        "&hourly=wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
        "&timezone=America%2FChicago"
        "&forecast_days=1"
        "&temperature_unit=fahrenheit"
        "&precipitation_unit=inch"
        "&windspeed_unit=mph"
    )
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()

        current = data['current']['temperature_2m']
        daily = data['daily']
        high = daily['temperature_2m_max'][0]
        low = daily['temperature_2m_min'][0]
        rain = daily['precipitation_sum'][0]
        wcode = daily['weather_code'][0]

        if rain == 0:
            rain_str = "0.00 inches expected"
        elif rain < 0.01:
            rain_str = "trace possible"
        else:
            rain_str = f"{rain:.2f} inches expected"

        storm_codes = {95, 96, 99}
        if wcode in storm_codes and rain > 0:
            rain_str += " (thunderstorm-dependent; totals uncertain)"

        # Current wind
        current_wind_speed = data['current']['wind_speed_10m']
        current_wind_dir = data['current']['wind_direction_10m']
        current_wind_str = f"{current_wind_speed:.1f} mph from the {wind_direction(current_wind_dir)}"

        # Daily average wind (scalar average of all hourly readings)
        hourly_wind = data['hourly']['wind_speed_10m']
        avg_wind = sum(hourly_wind) / len(hourly_wind) if hourly_wind else 0

        # Windiness percent
        wind_pct = ((avg_wind - WIND_MIN) / (WIND_MAX - WIND_MIN)) * 100

        return {
            'current': current,
            'high': high,
            'low': low,
            'rain_str': rain_str,
            'rain_raw': rain,
            'current_wind': current_wind_str,
            'avg_wind': avg_wind,
            'wind_pct': wind_pct,
        }
    except Exception as e:
        print(f"Weather fetch failed: {e}")
        return {
            'current': 'N/A',
            'high': 'N/A',
            'low': 'N/A',
            'rain_str': 'Unable to fetch weather data',
            'rain_raw': 'N/A',
            'current_wind': 'N/A',
            'avg_wind': 'N/A',
            'wind_pct': 'N/A',
        }

def send_ntfy_text(topic, message):
    """Send text notification."""
    url = f"https://ntfy.sh/{topic}"
    headers = {
        "Title": "Austin Sky + Weather",
        "Priority": "default",
        "Markdown": "yes",
    }
    try:
        response = requests.post(url, data=message.encode('utf-8'), headers=headers, timeout=30)
        response.raise_for_status()
        print("Text notification sent.")
    except Exception as e:
        print(f"Failed to send text: {e}")
        sys.exit(1)

def send_ntfy_image(topic, image_path, title):
    """Send image notification with raw image body."""
    url = f"https://ntfy.sh/{topic}"
    try:
        with open(image_path, 'rb') as f:
            headers = {
                "Content-Type": "image/png",
                "X-Title": title,
                "X-Priority": "default",
            }
            response = requests.post(url, data=f, headers=headers, timeout=30)
        response.raise_for_status()
        print("Image notification sent.")
    except Exception as e:
        print(f"Failed to send image: {e}")

# ==================== MAIN ====================

def main():
    if not NTFY_TOPIC:
        print("Error: NTFY_TOPIC environment variable is not set.")
        sys.exit(1)

    now = datetime.now(TZ)
    today = now.date()

    print(f"Running brief for {today}")

    # 6:15 AM datetimes
    today_615 = make_austin_dt(today.year, today.month, today.day, 6, 15)
    yesterday = today - timedelta(days=1)
    yesterday_615 = make_austin_dt(yesterday.year, yesterday.month, yesterday.day, 6, 15)
    tomorrow = today + timedelta(days=1)
    tomorrow_615 = make_austin_dt(tomorrow.year, tomorrow.month, tomorrow.day, 6, 15)

    # Twilight
    today_elev = sun_elevation_degrees(today_615)
    yesterday_elev = sun_elevation_degrees(yesterday_615)
    tomorrow_elev = sun_elevation_degrees(tomorrow_615)

    today_cat = twilight_category(today_elev)
    yesterday_cat = twilight_category(yesterday_elev)
    tomorrow_cat = twilight_category(tomorrow_elev)

    transition = ""
    if today_cat != yesterday_cat or tomorrow_cat != today_cat:
        parts = []
        if today_cat != yesterday_cat:
            parts.append(f"twilight category changed from {yesterday_cat.lower()} to {today_cat.lower()}")
        if tomorrow_cat != today_cat:
            parts.append(f"will change to {tomorrow_cat.lower()} tomorrow")
        transition = "Transition notice: " + "; ".join(parts)

    # Twilight duration for today's 6:15 AM category
    twilight_start, twilight_end, twilight_cat_name = twilight_interval_for_time(today_615)
    twilight_duration_line = ""
    if twilight_start and
