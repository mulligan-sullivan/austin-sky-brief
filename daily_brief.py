#!/usr/bin/env python3
"""
Austin Sky + Weather Daily Brief
Pushes to ntfy. Runs via GitHub Actions.
"""

import os
import sys
import math
import requests
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import time

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

# Temperature scale: 28.04°F = 0%, 91.81°F = 100%
# (averages of each year's lowest/highest daily-MEAN temperature,
# Austin 2016-2025, Open-Meteo archive; daily mean = average of hourly readings)
DAY_TEMP_MIN = 28.04
DAY_TEMP_MAX = 91.81

# Rain scale: 0 inches = 0%, 0.653 inches = 100%
RAIN_MAX = 0.653

# Wind scale: 2.64 mph = 0%, 18.37 mph = 100%
WIND_MIN = 2.64
WIND_MAX = 18.37

# Dew point scale: 8.35°F = 0%, 75.49°F = 100%
# (averages of each year's lowest/highest daily-mean dew point,
# Austin 2016-2025, Open-Meteo historical archive)
DEWPOINT_MIN = 8.35
DEWPOINT_MAX = 75.49

# Thermal solstice parameters from 10-year Austin climatology (2015-2024)
# Fitted: T(doy) = 15.98 * sin(2π·doy/365.25 - 1.972) + 71.06
THERMAL_AMPLITUDE = 15.98
THERMAL_MEAN = 71.06
THERMAL_PHASE = -1.972  # radians

THERMAL_EVENTS_CAL = [
    (1, 23, "coldness solstice"),
    (4, 24, "spring equinox"),
    (7, 24, "heat solstice"),
    (10, 23, "autumn equinox"),
]

# ==================== WILDFLOWERS ====================
# Bloom-season event dates derived from 10-year average bloom curves
# (2016-2025 iNaturalist research-grade observations, Austin; see
# wildflower_bloom_curves_2016_2025.csv). Thresholds follow BBCH/NPN
# convention: first flowers ~5% of seasonal peak, beginning of flowering
# >=10%, full bloom >=50%, peak bloom >=75%, past peak <75%,
# season closing <30%, last day = final day >=10% of peak,
# last flowers = final day >=5% of peak (symmetric with first flowers).
# Listed in chronological order of first flowers through the year.
WILDFLOWER_ORDER = [
    "Texas Bluebonnet",
    "Texas Paintbrush",
    "Pinkladies",
    "Turk's Cap",
    "Plains Coreopsis",
    "Black-Eyed Susan",
    "Snow-on-the-Mountain",
    "Maximilian Sunflower",
    "Narrow-Leaf Gayfeather",
    "Tall Goldenrod",
    "Toothleaf Goldeneye",
    "Aromatic Aster",
]

WILDFLOWER_EVENTS = {
    "Texas Bluebonnet": {
        "first_flowers": (2, 15),
        "beginning_flowering": (2, 22),
        "full_bloom": (3, 8),
        "peak_bloom": (3, 15),
        "past_peak": (4, 19),
        "season_closing": (5, 3),
        "last_day": (5, 10),
        "last_flowers": (5, 17),
        "ended": (5, 24),
    },
    "Texas Paintbrush": {
        "first_flowers": (2, 15),
        "beginning_flowering": (2, 22),
        "full_bloom": (3, 8),
        "peak_bloom": (3, 15),
        "past_peak": (4, 19),
        "season_closing": (5, 17),
        "last_day": (5, 24),
        "last_flowers": (5, 31),
        "ended": (6, 7),
    },
    "Pinkladies": {
        "first_flowers": (3, 1),
        "beginning_flowering": (3, 15),
        "full_bloom": (3, 22),
        "peak_bloom": (3, 29),
        "past_peak": (4, 26),
        "season_closing": (5, 10),
        "last_day": (5, 17),
        "last_flowers": (6, 28),
        "ended": (7, 5),
    },
    "Black-Eyed Susan": {
        "first_flowers": (4, 12),
        "beginning_flowering": (4, 19),
        "full_bloom": (4, 26),
        "peak_bloom": (5, 10),
        "past_peak": (5, 31),
        "season_closing": (6, 28),
        "last_day": (7, 5),
        "last_flowers": (7, 12),
        "ended": (7, 19),
    },
    "Plains Coreopsis": {
        "first_flowers": (4, 5),
        "beginning_flowering": (4, 12),
        "full_bloom": (5, 3),
        "peak_bloom": (5, 10),
        "past_peak": (5, 31),
        "season_closing": (6, 28),
        "last_day": (7, 5),
        "last_flowers": (7, 12),
        "ended": (7, 19),
    },
    "Aromatic Aster": {
        "first_flowers": (9, 27),
        "beginning_flowering": (10, 4),
        "full_bloom": (10, 11),
        "peak_bloom": (10, 18),
        "past_peak": (10, 25),
        "season_closing": (11, 22),
        "last_day": (12, 6),
        "last_flowers": (12, 20),
        "ended": (12, 27),
    },
    "Tall Goldenrod": {
        "first_flowers": (8, 9),
        "beginning_flowering": (9, 20),
        "full_bloom": (9, 27),
        "peak_bloom": (10, 4),
        "past_peak": (10, 25),
        "season_closing": (11, 1),
        "last_day": (12, 6),
        "last_flowers": (12, 31),
        "ended": (1, 7),
    },
    "Maximilian Sunflower": {
        "first_flowers": (8, 2),
        "beginning_flowering": (8, 23),
        "full_bloom": (10, 4),
        "peak_bloom": (10, 11),
        "past_peak": (10, 25),
        "season_closing": (11, 8),
        "last_day": (12, 6),
        "last_flowers": (12, 20),
        "ended": (12, 27),
    },
    "Narrow-Leaf Gayfeather": {
        "first_flowers": (8, 9),
        "beginning_flowering": (8, 16),
        "full_bloom": (8, 30),
        "peak_bloom": (9, 6),
        "past_peak": (9, 27),
        "season_closing": (11, 8),
        "last_day": (11, 22),
        "last_flowers": (11, 29),
        "ended": (12, 6),
    },
    "Snow-on-the-Mountain": {
        "first_flowers": (8, 2),
        "beginning_flowering": (8, 9),
        "full_bloom": (8, 30),
        "peak_bloom": (9, 6),
        "past_peak": (9, 20),
        "season_closing": (10, 18),
        "last_day": (11, 22),
        "last_flowers": (11, 29),
        "ended": (12, 6),
    },
    "Toothleaf Goldeneye": {
        "first_flowers": (9, 13),
        "beginning_flowering": (9, 20),
        "full_bloom": (10, 4),
        "peak_bloom": (10, 11),
        "past_peak": (11, 1),
        "season_closing": (12, 6),
        "last_day": (12, 20),
        "last_flowers": (12, 31),
        "ended": (1, 7),
    },
    "Turk's Cap": {
        "first_flowers": (3, 22),
        "beginning_flowering": (3, 29),
        "full_bloom": (8, 30),
        "peak_bloom": (9, 6),
        "past_peak": (9, 27),
        "season_closing": (11, 8),
        "last_day": (11, 29),
        "last_flowers": (12, 6),
        "ended": (12, 13),
    },
}

WILDFLOWER_LABELS = {
    "first_flowers": "First flowers",
    "beginning_flowering": "Beginning of flowering",
    "full_bloom": "Full bloom",
    "peak_bloom": "Peak bloom",
    "past_peak": "Past peak",
    "season_closing": "Season closing",
    "last_day": "Last day",
    "last_flowers": "Last flowers",
    "ended": "Season ended yesterday",
}

# ==================== PECANS ====================
# Pecans ripen by accumulated heat, not calendar. GDD base 50F: daily
# (max+min)/2 - 50, floored at 0, tallied from Jan 1 every morning.
# Thresholds calibrated on 2016-2025 iNaturalist pecan attention ramps +
# Open-Meteo archive temps (out-of-sample 2020/2023/2025 MAE 4.7 days;
# known failure mode: record-hot years like 2023 run ~11d early because
# extreme heat saturates kernel fill - hence "likely" on every label).
PECAN_GDD_CULTIVARS = 5697   # yard/improved trees, earlier
PECAN_GDD_NATIVE = 6138      # natives along creeks/riverbanks
PECAN_READY_DAYS = 21        # "likely ready" persists this long past crossing
PECAN_GLEAN_DAYS = 45        # then "likely gleanings" until this long past
# 2016-2025 mean cumulative GDD50 by week (climatological pace for the forecast)
PECAN_GDD_NORMAL_WEEKLY = [12, 42, 75, 103, 134, 190, 231, 287, 357, 443, 542, 641, 764, 887, 1010, 1148, 1287, 1452, 1622, 1802, 1997, 2201, 2408, 2635, 2875, 3113, 3356, 3601, 3854, 4111, 4364, 4621, 4886, 5147, 5395, 5633, 5848, 6072, 6292, 6483, 6675, 6839, 6992, 7104, 7222, 7309, 7396, 7460, 7517, 7564, 7609, 7662, 7698]

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
    'Mars': eph['mars'],
    'Jupiter': eph['jupiter barycenter'],
    'Saturn': eph['saturn barycenter'],
    'Uranus': eph['uranus barycenter'],
    'Neptune': eph['neptune barycenter'],
}

INNER_PLANETS = {
    'Mercury': eph['mercury'],
    'Venus': eph['venus'],
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

def find_rise_time(planet, start_dt, end_dt):
    """Find when planet first rises above horizon (alt >= 0) between start_dt and end_dt."""
    if start_dt is None or end_dt is None or start_dt >= end_dt:
        return None
    current = start_dt
    step = timedelta(minutes=2)
    prev_alt = None
    while current <= end_dt:
        alt, az = planet_position(planet, current)
        if prev_alt is not None and prev_alt < 0 and alt >= 0:
            return current
        prev_alt = alt
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
        "&current=temperature_2m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
        "&hourly=wind_speed_10m,dewpoint_2m,temperature_2m"
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

        # Wind: scalar average of all hourly readings for the day
        hourly_wind = data['hourly']['wind_speed_10m']
        avg_wind = sum(hourly_wind) / len(hourly_wind) if hourly_wind else 0

        # Dew point: scalar average of all hourly readings for the day
        hourly_dew = data['hourly']['dewpoint_2m']
        avg_dew = sum(hourly_dew) / len(hourly_dew) if hourly_dew else 'N/A'

        # Temperature: scalar average of all hourly readings for the day
        hourly_temp = data['hourly']['temperature_2m']
        avg_temp = sum(hourly_temp) / len(hourly_temp) if hourly_temp else 'N/A'

        if rain == 0:
            rain_str = "0.00 inches expected"
        elif rain < 0.01:
            rain_str = "trace possible"
        else:
            rain_str = f"{rain:.2f} inches expected"

        storm_codes = {95, 96, 99}
        if wcode in storm_codes and rain > 0:
            rain_str += " (thunderstorm-dependent; totals uncertain)"

        return {
            'current': current,
            'high': high,
            'low': low,
            'rain_str': rain_str,
            'rain_raw': rain,
            'avg_wind': avg_wind,
            'avg_dew': avg_dew,
            'avg_temp': avg_temp,
        }
    except Exception as e:
        print(f"Weather fetch failed: {e}")
        return {
            'current': 'N/A',
            'high': 'N/A',
            'low': 'N/A',
            'rain_str': 'Unable to fetch weather data',
            'rain_raw': 'N/A',
            'avg_wind': 'N/A',
            'avg_dew': 'N/A',
            'avg_temp': 'N/A',
        }

def send_ntfy_text(topic, message, title="Austin Sky + Weather"):
    """Send text notification."""
    url = f"https://ntfy.sh/{topic}"
    headers = {
        "Title": title,
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

# ==================== THERMAL HELPERS ====================

def thermal_solstice_pct(doy):
    """Return thermal solstice percentage for a given day-of-year.
    +100% = thermal summer solstice (~July 24)
    0%    = thermal equinoxes (~Apr 24, ~Oct 23)
    -100% = thermal winter solstice (~Jan 23)
    """
    pct = math.sin(2 * math.pi * doy / 365.25 + THERMAL_PHASE) * 100
    return pct

def thermal_event_annotation(doy, today_dt):
    """Return proximity annotation for the closest thermal event, if any."""
    annotations = []
    today_month = today_dt.month
    today_day = today_dt.day
    
    for event_month, event_day, name in THERMAL_EVENTS_CAL:
        # Calendar "a month from today" — exact same calendar day, previous month
        month_before = event_month - 1
        if month_before == 0:
            month_before = 12
        if today_month == month_before and today_day == event_day:
            annotations.append((0, f"{name} a month from today"))
            continue
        
        # DOY distance-based checks
        event_doy = datetime(2024, event_month, event_day).timetuple().tm_yday
        days_until = event_doy - doy
        if days_until < 0:
            days_until += 365.25
        days_since = doy - event_doy
        if days_since < 0:
            days_since += 365.25
        
        du = round(days_until)
        ds = round(days_since)
        
        if du == 0:
            annotations.append((0, name))
        elif du == 1:
            annotations.append((1, f"{name} tomorrow"))
        elif 2 <= du <= 7:
            annotations.append((du, f"{name} this week"))
        elif 8 <= du <= 14:
            annotations.append((du, f"{name} next week"))
        elif 15 <= du <= 21:
            annotations.append((du, f"{name} two weeks away"))
        
        if ds == 1:
            annotations.append((ds, f"{name} yesterday"))
        elif 2 <= ds <= 7:
            annotations.append((ds, f"{name} in the past week"))
    
    if not annotations:
        return ""
    
    best = min(annotations, key=lambda x: x[0])
    return f" — {best[1]}"

# ==================== INNER PLANET HELPERS ====================

def find_sunrise_sunset(date_dt):
    """Find sunrise and sunset times for the given date."""
    noon = datetime(date_dt.year, date_dt.month, date_dt.day, 12, 0, tzinfo=TZ)
    t0 = ts.from_datetime(noon - timedelta(hours=14))
    t1 = ts.from_datetime(noon + timedelta(hours=14))
    
    f = almanac.sunrise_sunset(eph, austin)
    times, events = almanac.find_discrete(t0, t1, f)
    
    sunrise = None
    sunset = None
    for ti, event in zip(times, events):
        dt_local = ti.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
        if event == 1 and sunrise is None:
            sunrise = dt_local
        elif event == 0 and sunset is None:
            sunset = dt_local
    
    return sunrise, sunset

def elongation_at(dt, planet):
    """Return angular separation (degrees) between planet and Sun at dt."""
    t = ts.from_datetime(dt)
    sun_app = observer.at(t).observe(sun).apparent()
    planet_app = observer.at(t).observe(planet).apparent()
    return sun_app.separation_from(planet_app).degrees

def find_inner_planet_events(planet, start_dt, days=730):
    """
    Find greatest elongations and conjunctions for an inner planet
    over a ~2-year window. Returns list of (dt, event_type, detail).
    """
    events = []
    
    # Sample every 6 hours for precision
    samples = []
    current = start_dt
    end = start_dt + timedelta(days=days)
    while current <= end:
        samples.append((current, elongation_at(current, planet)))
        current += timedelta(hours=6)
    
    # Find extrema
    for i in range(2, len(samples) - 2):
        prev_elong = samples[i-1][1]
        curr_elong = samples[i][1]
        next_elong = samples[i+1][1]
        
        # Local maximum = greatest elongation
        if curr_elong > prev_elong and curr_elong > next_elong and curr_elong > 15:
            refine_start = samples[i-1][0]
            refine_end = samples[i+1][0]
            best_dt, best_elong = _refine_extremum(planet, refine_start, refine_end, find_max=True)
            
            # Determine east vs west by checking position relative to Sun
            t = ts.from_datetime(best_dt)
            sun_app = observer.at(t).observe(sun).apparent()
            planet_app = observer.at(t).observe(planet).apparent()
            sun_lon = sun_app.ecliptic_latlon(epoch=None)[1].degrees
            planet_lon = planet_app.ecliptic_latlon(epoch=None)[1].degrees
            diff = (planet_lon - sun_lon + 180) % 360 - 180
            
            if diff > 0:
                # East of Sun = evening star
                events.append((best_dt, "evening_star_max", "evening star, max elongation"))
            else:
                # West of Sun = morning star
                events.append((best_dt, "morning_star_max", "morning star, max elongation"))
        
        # Local minimum = conjunction
        elif curr_elong < prev_elong and curr_elong < next_elong and curr_elong < 5:
            refine_start = samples[i-1][0]
            refine_end = samples[i+1][0]
            best_dt, best_elong = _refine_extremum(planet, refine_start, refine_end, find_max=False)
            
            # Classify as superior or inferior
            after_dt = best_dt + timedelta(days=5)
            t_after = ts.from_datetime(after_dt)
            sun_app = observer.at(t_after).observe(sun).apparent()
            planet_app = observer.at(t_after).observe(planet).apparent()
            sun_lon = sun_app.ecliptic_latlon(epoch=None)[1].degrees
            planet_lon = planet_app.ecliptic_latlon(epoch=None)[1].degrees
            diff = (planet_lon - sun_lon + 180) % 360 - 180
            
            if diff > 0:
                # Becoming evening star → this was superior conjunction
                events.append((best_dt, "superior_conjunction", "superior conjunction"))
            else:
                # Becoming morning star → this was inferior conjunction
                events.append((best_dt, "inferior_conjunction", "inferior conjunction"))
    
    # Remove duplicates and sort
    seen = set()
    unique = []
    for e in sorted(events, key=lambda x: x[0]):
        key = (e[0].strftime('%Y-%m-%d'), e[1])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    
    return unique

def _refine_extremum(planet, start_dt, end_dt, find_max=True):
    """Refine an extremum by binary search."""
    best_dt = start_dt
    best_val = elongation_at(start_dt, planet)
    
    current = start_dt
    while current <= end_dt:
        val = elongation_at(current, planet)
        if find_max:
            if val > best_val:
                best_val = val
                best_dt = current
        else:
            if val < best_val:
                best_val = val
                best_dt = current
        current += timedelta(hours=1)
    
    return best_dt, best_val

def find_opposition_events(planet, start_dt, days=1460):
    """Find opposition events for an outer planet over a ~4-year window."""
    events = []
    
    # Sample every 12 hours
    samples = []
    current = start_dt
    end = start_dt + timedelta(days=days)
    while current <= end:
        t = ts.from_datetime(current)
        sun_app = observer.at(t).observe(sun).apparent()
        planet_app = observer.at(t).observe(planet).apparent()
        sun_lon = sun_app.ecliptic_latlon(epoch=None)[1].degrees
        planet_lon = planet_app.ecliptic_latlon(epoch=None)[1].degrees
        diff = (planet_lon - sun_lon + 180) % 360 - 180
        samples.append((current, diff))
        current += timedelta(hours=12)
    
    # Find zero crossings of diff = 0 (opposition)
    for i in range(len(samples) - 1):
        if samples[i][1] * samples[i+1][1] < 0:  # Sign change = crossing 180°
            # Refine
            best_dt = samples[i][0]
            best_diff = abs(samples[i][1])
            current = samples[i][0]
            while current <= samples[i+1][0]:
                t = ts.from_datetime(current)
                sun_app = observer.at(t).observe(sun).apparent()
                planet_app = observer.at(t).observe(planet).apparent()
                sun_lon = sun_app.ecliptic_latlon(epoch=None)[1].degrees
                planet_lon = planet_app.ecliptic_latlon(epoch=None)[1].degrees
                diff = (planet_lon - sun_lon + 180) % 360 - 180
                if abs(diff) < best_diff:
                    best_diff = abs(diff)
                    best_dt = current
                current += timedelta(hours=1)
            
            events.append((best_dt, "opposition", "opposition"))
    
    # Remove duplicates
    seen = set()
    unique = []
    for e in sorted(events, key=lambda x: x[0]):
        key = e[0].strftime('%Y-%m-%d')
        if key not in seen:
            seen.add(key)
            unique.append(e)
    
    return unique

def outer_planet_event_annotation(today_dt, events):
    """Return proximity annotation for outer planet events (opposition).
    Full Venus-style schedule.
    """
    annotations = []
    today_month = today_dt.month
    today_day = today_dt.day
    
    for event_dt, etype, detail in events:
        event_month = event_dt.month
        event_day = event_dt.day
        
        days_until = (event_dt - today_dt).total_seconds() / 86400
        days_since = (today_dt - event_dt).total_seconds() / 86400
        
        du = round(days_until)
        ds = round(days_since)
        
        # Calendar "a month from today"
        month_before = event_month - 1
        if month_before == 0:
            month_before = 12
        if today_month == month_before and today_day == event_day:
            annotations.append((0, f"{detail} a month from today"))
            continue
        
        if du == 0:
            annotations.append((0, detail))
        elif du == 1:
            annotations.append((1, f"{detail} tomorrow"))
        elif 2 <= du <= 7:
            annotations.append((du, f"{detail} this week"))
        elif 8 <= du <= 14:
            annotations.append((du, f"{detail} next week"))
        elif 15 <= du <= 21:
            annotations.append((du, f"{detail} two weeks away"))
        
        if ds == 1:
            annotations.append((ds, f"{detail} yesterday"))
        elif 2 <= ds <= 7:
            annotations.append((ds, f"{detail} in the past week"))
    
    if not annotations:
        return ""
    
    best = min(annotations, key=lambda x: x[0])
    return f" — {best[1]}"

def inner_planet_status(name, planet, today_dt):
    """
    Return current status info for Mercury or Venus.
    Returns dict with: status, events
    """
    # Find events in a 2-year window
    events = find_inner_planet_events(planet, today_dt - timedelta(days=365), days=730)
    
    # All events get notifications (both conjunctions + both max elongations)
    notify_events = [(dt, etype, detail) for dt, etype, detail in events 
                     if etype in ('superior_conjunction', 'inferior_conjunction', 
                                  'evening_star_max', 'morning_star_max')]
    
    # Determine current phase
    today_elong = elongation_at(today_dt, planet)
    
    # Check if near any conjunction (elongation < 10° and within window)
    # Mercury moves fast: ~7 day window. Venus moves slow: ~30 day window.
    in_conjunction = False
    conj_end = None
    next_phase = None
    conj_type = None
    conj_window = 7 if name == 'Mercury' else 30
    
    # Find the closest conjunction event
    closest_conj = None
    closest_diff = float('inf')
    for dt, etype, detail in events:
        if etype in ('superior_conjunction', 'inferior_conjunction'):
            diff = abs((today_dt - dt).total_seconds() / 86400)
            if diff < closest_diff:
                closest_diff = diff
                closest_conj = (dt, etype, detail)
    
    if closest_conj:
        dt, etype, detail = closest_conj
        if closest_diff < conj_window and today_elong < 10:
            in_conjunction = True
            conj_type = detail
            # Find what comes next after this conjunction
            for dt2, etype2, detail2 in events:
                if dt2 > dt and etype2 in ('evening_star_max', 'morning_star_max'):
                    conj_end = dt2
                    next_phase = detail2.split(',')[0]  # "evening star" or "morning star"
                    break
    
    sunrise, sunset = find_sunrise_sunset(today_dt)
    
    if in_conjunction and next_phase:
        # Find actual end of conjunction: when planet first reaches 5° altitude
        # at sunrise (morning star) or sunset (evening star). Search forward.
        if closest_conj:
            conj_dt = closest_conj[0]
            search_start = conj_dt
            search_end = conj_dt + timedelta(days=60)
            current = search_start
            end_date = None
            
            # Determine which twilight to check based on next phase
            check_sunset = (next_phase == "evening star")
            
            while current <= search_end:
                # Get sunrise/sunset for this day
                dt_noon = datetime(current.year, current.month, current.day, 12, 0, tzinfo=TZ)
                t0 = ts.from_datetime(dt_noon - timedelta(hours=14))
                t1 = ts.from_datetime(dt_noon + timedelta(hours=14))
                f = almanac.sunrise_sunset(eph, austin)
                times, events = almanac.find_discrete(t0, t1, f)
                
                twilight_time = None
                for ti, event in zip(times, events):
                    dt_local = ti.utc_datetime().replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
                    if check_sunset and event == 0:
                        twilight_time = dt_local
                        break
                    elif not check_sunset and event == 1:
                        twilight_time = dt_local
                        break
                
                if twilight_time:
                    t_twilight = ts.from_datetime(twilight_time)
                    apparent = observer.at(t_twilight).observe(planet).apparent()
                    alt, az, _ = apparent.altaz()
                    if alt.degrees >= 5:
                        end_date = twilight_time
                        break
                
                current += timedelta(days=1)
            
            if end_date:
                end_str = end_date.strftime("%B %-d")
                status = f"{conj_type} until ~{end_str}, then {next_phase}"
            else:
                status = f"{conj_type}, then {next_phase}"
        else:
            status = f"{conj_type}, then {next_phase}"
    else:
        # Check if evening or morning star
        t = ts.from_datetime(today_dt)
        sun_app = observer.at(t).observe(sun).apparent()
        planet_app = observer.at(t).observe(planet).apparent()
        sun_lon = sun_app.ecliptic_latlon(epoch=None)[1].degrees
        planet_lon = planet_app.ecliptic_latlon(epoch=None)[1].degrees
        diff = (planet_lon - sun_lon + 180) % 360 - 180
        
        if diff > 0:
            # East of Sun = evening star
            if sunset:
                alt, az = planet_position(planet, sunset)
                # Check trend: compare today's sunset alt vs tomorrow's
                tomorrow_sunset = sunset + timedelta(days=1)
                t_tomorrow = ts.from_datetime(tomorrow_sunset)
                tomorrow_app = observer.at(t_tomorrow).observe(planet).apparent()
                tomorrow_alt, _, _ = tomorrow_app.altaz()
                trend = ", rising" if tomorrow_alt.degrees > alt else ", sinking"
                
                if alt >= 0:
                    planet_set = find_set_time(planet, sunset, sunset + timedelta(hours=12))
                    if planet_set:
                        status = f"evening star{trend}, {alt:.0f}° at sunset (sets {format_time(planet_set)})"
                    else:
                        status = f"evening star{trend}, {alt:.0f}° at sunset"
                else:
                    status = f"evening star{trend}, below horizon at sunset"
            else:
                status = "evening star"
        else:
            # West of Sun = morning star
            if sunrise:
                alt, az = planet_position(planet, sunrise)
                # Check trend: compare today's sunrise alt vs tomorrow's
                tomorrow_sunrise = sunrise + timedelta(days=1)
                t_tomorrow = ts.from_datetime(tomorrow_sunrise)
                tomorrow_app = observer.at(t_tomorrow).observe(planet).apparent()
                tomorrow_alt, _, _ = tomorrow_app.altaz()
                trend = ", rising" if tomorrow_alt.degrees > alt else ", sinking"
                
                if alt >= 0:
                    planet_rise = find_rise_time(planet, sunrise - timedelta(hours=12), sunrise)
                    if planet_rise:
                        status = f"morning star{trend}, {alt:.0f}° at sunrise (rises {format_time(planet_rise)})"
                    else:
                        status = f"morning star{trend}, {alt:.0f}° at sunrise"
                else:
                    status = f"morning star{trend}, below horizon at sunrise"
            else:
                status = "morning star"
    
    return {
        'status': status,
        'events': notify_events,
    }

def inner_planet_event_annotation(name, today_dt, events, current_status=""):
    """Return proximity annotation for inner planet events.
    Mercury: in 3 days, in 2 days, tomorrow, today | yesterday
    Venus: full schedule like thermal
    """
    annotations = []
    today_month = today_dt.month
    today_day = today_dt.day
    
    # If currently in conjunction, don't show conjunction annotations (status already says it)
    status_lower = current_status.lower()
    in_conj_now = "conjunction" in status_lower
    
    for event_dt, etype, detail in events:
        # Skip conjunction annotations if status already shows we're in one
        if in_conj_now and "conjunction" in detail.lower():
            continue
        
        event_month = event_dt.month
        event_day = event_dt.day
        
        days_until = (event_dt - today_dt).total_seconds() / 86400
        days_since = (today_dt - event_dt).total_seconds() / 86400
        
        du = round(days_until)
        ds = round(days_since)
        
        if name == 'Mercury':
            # Mercury: tight window
            if du == 0:
                annotations.append((0, detail))
            elif du == 1:
                annotations.append((1, f"{detail} tomorrow"))
            elif du == 2:
                annotations.append((2, f"{detail} in 2 days"))
            elif du == 3:
                annotations.append((3, f"{detail} in 3 days"))
            
            if ds == 1:
                annotations.append((ds, f"end of {detail} yesterday"))
        
        else:
            # Venus: full schedule
            # Calendar "a month from today"
            month_before = event_month - 1
            if month_before == 0:
                month_before = 12
            if today_month == month_before and today_day == event_day:
                annotations.append((0, f"{detail} a month from today"))
                continue
            
            if du == 0:
                annotations.append((0, detail))
            elif du == 1:
                annotations.append((1, f"{detail} tomorrow"))
            elif 2 <= du <= 7:
                annotations.append((du, f"{detail} this week"))
            elif 8 <= du <= 14:
                annotations.append((du, f"{detail} next week"))
            elif 15 <= du <= 21:
                annotations.append((du, f"{detail} two weeks away"))
            
            if ds == 1:
                annotations.append((ds, f"end of {detail} yesterday"))
            elif 2 <= ds <= 7:
                annotations.append((ds, f"end of {detail} in the past week"))
    
    if not annotations:
        return ""
    
    best = min(annotations, key=lambda x: x[0])
    return f" — {best[1]}"


# ==================== WILDFLOWER HELPERS ====================

def wildflower_status(events, today_dt):
    """Return today's label for one wildflower species, or None if inactive."""
    def doy(m, d):
        return datetime(2024, m, d).timetuple().tm_yday

    def dist(a, b):
        d = b - a
        return d + 365 if d < -180 else d

    td = doy(today_dt.month, today_dt.day)

    # Warnings before the season opens
    du = dist(td, doy(*events["first_flowers"]))
    if du == 1:
        return "First flowers tomorrow"
    if 2 <= du <= 7:
        return "First flowers next week"

    ff = doy(*events["first_flowers"])
    bf = doy(*events["beginning_flowering"])
    fb = doy(*events["full_bloom"])
    pb = doy(*events["peak_bloom"])
    pp = doy(*events["past_peak"])
    sc = doy(*events["season_closing"])
    ld = doy(*events["last_day"])
    lf = doy(*events["last_flowers"])
    end = doy(*events["ended"])

    if dist(td, end) == 0:
        return "Season ended yesterday"
    if dist(td, lf) == 0:
        return "Last flowers"
    if dist(td, ld) == 0:
        return "Last day"
    if dist(td, sc) == 0:
        return "Season closing"
    if dist(td, pp) == 0:
        return "Past peak"
    if dist(td, pb) == 0:
        return "Peak bloom"
    if dist(td, fb) == 0:
        return "Full bloom"
    if dist(td, ff) == 0:
        return "First flowers"
    if ff <= td <= bf:
        return "Beginning of flowering"
    if bf < td <= fb:
        return "Full bloom"
    if fb < td <= pp:
        return "Peak bloom"
    if pp < td <= sc:
        return "Past peak"
    if sc < td <= ld:
        return "Season closing"
    if ld < td <= lf:
        return "Last flowers"
    return None

# ==================== PECAN HELPERS ====================

def _pecan_season_tally(today):
    """Season-to-date GDD50 for Austin: archive through ~5 days ago,
    forecast API for the last week (splice on date to avoid overlap)."""
    def add(tmaxs, tmins):
        return sum(max(0.0, (hi + lo) / 2.0 - 50.0)
                   for hi, lo in zip(tmaxs, tmins) if hi is not None and lo is not None)

    tally = 0.0
    jan1 = date(today.year, 1, 1)
    archive_end = today - timedelta(days=6)
    seen = set()
    if archive_end >= jan1:
        u1 = ("https://archive-api.open-meteo.com/v1/archive?latitude=30.2672&longitude=-97.7431"
              f"&start_date={jan1}&end_date={archive_end}"
              "&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=America%2FChicago")
        try:
            d1 = requests.get(u1, timeout=30).json()['daily']
            seen = set(d1['time'])
            tally += add(d1['temperature_2m_max'], d1['temperature_2m_min'])
        except Exception as e:
            print(f"Pecan archive fetch failed: {e}")
    u2 = ("https://api.open-meteo.com/v1/forecast?latitude=30.2672&longitude=-97.7431"
          "&daily=temperature_2m_max,temperature_2m_min&past_days=7"
          "&temperature_unit=fahrenheit&timezone=America%2FChicago")
    try:
        d2 = requests.get(u2, timeout=30).json()['daily']
        hi = [h for t, h in zip(d2['time'], d2['temperature_2m_max']) if t not in seen]
        lo = [l for t, l in zip(d2['time'], d2['temperature_2m_min']) if t not in seen]
        tally += add(hi, lo)
    except Exception as e:
        print(f"Pecan forecast fetch failed: {e}")
    return tally

def _pecan_normal_cross_doy(threshold):
    """Day-of-year the climatological tally reaches a threshold (interpolated
    in the weekly normal table). Fallbacks if the table is ever empty."""
    if not PECAN_GDD_NORMAL_WEEKLY:
        return 248 if threshold == PECAN_GDD_CULTIVARS else 262
    for i in range(1, len(PECAN_GDD_NORMAL_WEEKLY)):
        if PECAN_GDD_NORMAL_WEEKLY[i] >= threshold:
            prev, cur = PECAN_GDD_NORMAL_WEEKLY[i - 1], PECAN_GDD_NORMAL_WEEKLY[i]
            frac = (threshold - prev) / (cur - prev) if cur > prev else 0
            return (i - 1) * 7 + round(frac * 7)
    return 364

def _pecan_days_out(tally, threshold, today):
    """Days until the season tally reaches threshold at climatological pace."""
    if tally >= threshold:
        return 0
    need = threshold - tally
    days = 0
    doy = today.timetuple().tm_yday
    while need > 0 and days < 250:
        if PECAN_GDD_NORMAL_WEEKLY:
            wk = min((doy + days - 1) // 7, 51)
            rate = (PECAN_GDD_NORMAL_WEEKLY[wk + 1] - PECAN_GDD_NORMAL_WEEKLY[wk]) / 7.0
        else:
            rate = 31.0
        need -= rate
        days += 1
    return days

def pecan_lines(now, today):
    """One label per indicator, in year order: Cultivars first (earlier),
    then Native trees. Six labels, mutually exclusive."""
    tally = _pecan_season_tally(today)
    doy = today.timetuple().tm_yday
    lines = []
    for label, threshold in (("Cultivars", PECAN_GDD_CULTIVARS),
                             ("Native trees", PECAN_GDD_NATIVE)):
        cross = _pecan_normal_cross_doy(threshold)
        if doy == cross + PECAN_GLEAN_DAYS + 1:
            lines.append(f"- {label}: season likely over yesterday")
        elif tally >= threshold:
            if doy <= cross + PECAN_READY_DAYS:
                lines.append(f"- {label}: likely ready")
            elif doy <= cross + PECAN_GLEAN_DAYS:
                lines.append(f"- {label}: likely gleanings")
        else:
            days_out = _pecan_days_out(tally, threshold, today)
            if 15 <= days_out <= 21:
                lines.append(f"- {label}: likely ready in 3 weeks")
            elif 8 <= days_out <= 14:
                lines.append(f"- {label}: likely ready in 2 weeks")
            elif 1 <= days_out <= 7:
                lines.append(f"- {label}: likely ready next week")
    return lines

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
    if twilight_start and twilight_end:
        twilight_duration_line = f"Today {twilight_cat_name.lower()} lasts from about {format_time(twilight_start)} to {format_time(twilight_end)}."

    # Generate twilight chart
    chart_path = "./twilight_chart.png"
    chart_ready = False
    try:
        generate_twilight_chart(today, today_615, chart_path)
        chart_ready = os.path.exists(chart_path)
    except Exception as e:
        print(f"Chart generation failed: {e}")

    # Moon
    moon_info = get_moon_info(today_615)
    
    # Moon position at 6:15 AM
    moon_alt, moon_az = planet_position(moon, today_615)
    if moon_alt >= 0:
        moon_pos_line = f"at 6:15 AM: {format_alt_dir(moon_alt, moon_az)}."
    else:
        next_rise = find_next_moonrise(today_615)
        if next_rise:
            moon_pos_line = f"at 6:15 AM: below the horizon, next rises at {format_time(next_rise)}."
        else:
            moon_pos_line = "at 6:15 AM: below the horizon."

    # Planets (outer only — Mercury and Venus handled separately)
    time_21 = make_austin_dt(today.year, today.month, today.day, 21, 0)
    night_start, night_end = find_proper_night_bounds(today)

    above_threshold_21 = []
    reach_threshold_data = []  # (first_hit_time, formatted_string)
    not_reach_names = []

    for name, planet in PLANETS.items():
        alt_21, az_21 = planet_position(planet, time_21)
        
        if alt_21 >= ALTITUDE_THRESHOLD:
            # Already above threshold at 9:00 PM — show actual position, then find when it sets
            pos_21 = format_alt_dir(alt_21, az_21)
            set_time = find_set_time(planet, time_21, night_end)
            if set_time:
                above_threshold_21.append(f"- {name}: {pos_21} at 9:00 PM, sets at {format_time(set_time)}")
            else:
                # Does not set overnight — report 6:15 AM position
                alt_615, az_615 = planet_position(planet, today_615)
                above_threshold_21.append(f"- {name}: {pos_21} at 9:00 PM, at 6:15 AM: {format_alt_dir(alt_615, az_615)}")
            continue
        
        # Not above threshold at 9:00 PM — check overnight
        first_hit = find_first_threshold(planet, night_start, night_end, ALTITUDE_THRESHOLD)
        if first_hit:
            drop_time = find_drop_below_threshold(planet, first_hit, night_end, ALTITUDE_THRESHOLD)
            if drop_time:
                line = f"- {name}: {format_time(first_hit)} (drops below {ALTITUDE_THRESHOLD}° by {format_time(drop_time)})"
            else:
                # Still above threshold at end of night — report 6:15 AM altitude and direction
                alt_615, az_615 = planet_position(planet, today_615)
                line = f"- {name}: {format_time(first_hit)} (at 6:15 AM: {format_alt_dir(alt_615, az_615)})"
            reach_threshold_data.append((first_hit, line))
        else:
            not_reach_names.append(name)

    # Sort overnight risers by time they first reach threshold
    reach_threshold_data.sort(key=lambda x: x[0])
    reach_threshold_lines = [item[1] for item in reach_threshold_data]

    # Inner planets (Mercury & Venus)
    inner_planet_data = {}
    for name, planet in INNER_PLANETS.items():
        inner_planet_data[name] = inner_planet_status(name, planet, now)
    
    # Outer planet opposition events
    outer_planet_events = {}
    for name, planet in PLANETS.items():
        outer_planet_events[name] = find_opposition_events(planet, now - timedelta(days=365), days=730)

    # Weather
    weather = get_weather()

    # Calculated percentages
    if weather['avg_temp'] != 'N/A':
        day_temp_pct = ((weather['avg_temp'] - DAY_TEMP_MIN) / (DAY_TEMP_MAX - DAY_TEMP_MIN)) * 100
        day_temp_line = f"- Temperature percent: {day_temp_pct:.1f}%"
    else:
        day_temp_line = "- Temperature percent: N/A"

    if weather['rain_raw'] != 'N/A':
        rain_pct = (weather['rain_raw'] / RAIN_MAX) * 100
        rain_pct_line = f"- Wetness percent: {rain_pct:.1f}%"
    else:
        rain_pct_line = "- Wetness percent: N/A"

    # Wind lines
    if weather['avg_wind'] != 'N/A':
        wind_avg_line = f"- Average wind today: {weather['avg_wind']:.1f} mph"
        wind_pct = ((weather['avg_wind'] - WIND_MIN) / (WIND_MAX - WIND_MIN)) * 100
        wind_pct = min(100, max(0, wind_pct))
        wind_pct_line = f"- Windiness percent: {wind_pct:.1f}%"
    else:
        wind_avg_line = "- Average wind today: N/A"
        wind_pct_line = "- Windiness percent: N/A"

    # Thermal solstice
    doy = now.timetuple().tm_yday
    thermal_pct = thermal_solstice_pct(doy)
    thermal_trend = "cooling" if thermal_pct > 0 else "warming"
    thermal_anno = thermal_event_annotation(doy, now)
    thermal_line = f"- Avg. thermal solstice: {thermal_pct:+.0f}% ({thermal_trend}){thermal_anno}"

    # Dew point lines
    if weather['avg_dew'] != 'N/A':
        dew_line = f"- Avg. dew point today: {weather['avg_dew']:.1f}°F"
        dew_pct = ((weather['avg_dew'] - DEWPOINT_MIN) / (DEWPOINT_MAX - DEWPOINT_MIN)) * 100
        dew_pct_line = f"- Dew point percent: {dew_pct:.1f}%"
    else:
        dew_line = "- Avg. dew point today: N/A"
        dew_pct_line = "- Dew point percent: N/A"

    # Build report with explicit spacing
    weekday = today.strftime("%A")
    month_day = today.strftime("%B %-d")
    year = today.year

    report = f"## Austin Sky + Weather — {weekday}, {month_day}, {year}\n\n"
    report += f"### Twilight at 6:15 AM\n\n"

    if transition:
        report += f"{transition}\n\n"

    report += f"Today: {twilight_line(today_elev)}\n"
    report += f"Yesterday: {twilight_line(yesterday_elev)}\n"
    report += f"Tomorrow: {twilight_line(tomorrow_elev)}\n\n"

    if twilight_duration_line:
        report += f"{twilight_duration_line}\n\n"

    report += f"### Moon\n\n"
    report += f"{moon_info}\n"
    report += f"{moon_pos_line}\n\n"
    report += f"### Planets\n\n"

    if above_threshold_21:
        report += f"Above {ALTITUDE_THRESHOLD}° at 9:00 PM today:\n\n"
        annotated = []
        for line in above_threshold_21:
            # Extract planet name from line like "- Mars: ..."
            name = line[2:].split(":")[0]
            anno = outer_planet_event_annotation(now, outer_planet_events.get(name, []))
            annotated.append(line + anno)
        report += "\n".join(annotated) + "\n\n"

    if reach_threshold_lines:
        report += f"Reaches {ALTITUDE_THRESHOLD}° altitude during the night (not above {ALTITUDE_THRESHOLD}° at 9:00 PM):\n\n"
        annotated = []
        for line in reach_threshold_lines:
            name = line[2:].split(":")[0]
            anno = outer_planet_event_annotation(now, outer_planet_events.get(name, []))
            annotated.append(line + anno)
        report += "\n".join(annotated) + "\n\n"

    if not_reach_names:
        report += f"Not above {ALTITUDE_THRESHOLD}° at 9:00 PM, and does not reach {ALTITUDE_THRESHOLD}° overnight:\n\n"
        annotated = []
        for name in not_reach_names:
            anno = outer_planet_event_annotation(now, outer_planet_events.get(name, []))
            if anno:
                annotated.append(f"{name}{anno}")
            else:
                annotated.append(name)
        report += ", ".join(annotated) + "\n\n"

    # Inner planets subsection
    report += "**Inner planets**\n\n"
    for name in ['Mercury', 'Venus']:
        data = inner_planet_data[name]
        anno = inner_planet_event_annotation(name, now, data['events'], data['status'])
        report += f"- {name}: {data['status']}{anno}\n"
    report += "\n"

    report += f"### Weather\n\n"
    report += f"- Current temperature: {weather['current']}°F\n"
    report += f"- Expected high: {weather['high']}°F\n"
    report += f"- Expected low: {weather['low']}°F\n"
    report += f"{day_temp_line}\n"
    report += f"{thermal_line}\n"
    report += f"{dew_line}\n"
    report += f"{dew_pct_line}\n"
    report += f"- Rain: {weather['rain_str']}\n"
    report += f"{rain_pct_line}\n"
    report += f"{wind_avg_line}\n"
    report += f"{wind_pct_line}\n\n"
    # Nature section - Pecans above Wildflowers; printed only when something is active
    pecan = pecan_lines(now, today)
    wildflower_lines = []
    for wf_name in WILDFLOWER_ORDER:
        status = wildflower_status(WILDFLOWER_EVENTS[wf_name], now)
        if status:
            wildflower_lines.append(f"- {wf_name}: {status}")
    if pecan or wildflower_lines:
        report += "### Nature\n\n"
        if pecan:
            report += "**Pecans**\n\n"
            report += "\n".join(pecan) + "\n\n"
        if wildflower_lines:
            report += "**Wildflowers**\n\n"
            report += "\n".join(wildflower_lines) + "\n\n"

    report += f"Sources: Skyfield (JPL DE421 ephemeris), Open-Meteo"

    print(report)
    
    # Send report in two halves, second half FIRST. In ntfy, the newest
    # message sits on top, so the stack reads: image on top, then the report
    # beginning, then Weather/Wildflowers below.
    split_marker = "### Weather"
    split_at = report.index(split_marker)
    second_half = report[split_at:]
    first_half = report[:split_at]

    send_ntfy_text(NTFY_TOPIC, second_half, title="Austin Sky + Weather - forecast & blooms")
    time.sleep(3)
    send_ntfy_text(NTFY_TOPIC, first_half)
    time.sleep(3)
    
    # Send chart last so it lands on top of the notification stack
    if chart_ready:
        send_ntfy_image(NTFY_TOPIC, chart_path, "Twilight at 6:15 AM")

if __name__ == "__main__":
    main()
