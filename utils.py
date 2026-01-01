import re
import csv
from datetime import datetime, timedelta
# Import DB functions needed for logic
from database import load_schedule_from_db, cursor

# --- Data Sources ---
LOCATIONS = {
    "Gauteng": {
        "City of Johannesburg": ["Sandton", "Soweto", "Johannesburg", "Midrand", "Roodepoort", "Randburg"],
        "City of Tshwane": ["Pretoria", "Centurion"],
        "Ekurhuleni": ["Benoni", "Boksburg", "Kempton Park", "Germiston", "Alberton", "Springs", "Brakpan"],
        "Mogale City": ["Krugersdorp"],
        "Emfuleni": ["Vereeniging"]
    },
    "Limpopo": {
        "Polokwane": ["Polokwane"]
    }
}

def get_valid_areas():
    areas = set()
    for prov in LOCATIONS:
        for muni in LOCATIONS[prov]:
            for area in LOCATIONS[prov][muni]:
                areas.add(area)
    return areas

def validate_csv(file_path):
    time_pattern = re.compile(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]\s*-\s*([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    valid_areas = get_valid_areas()
    
    try:
        with open(file_path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            if "area" not in reader.fieldnames or "time_slot" not in reader.fieldnames:
                return False, "CSV missing 'area' or 'time_slot' columns"
            
            for line_num, row in enumerate(reader, start=2): # Start 2 to account for header
                area = row.get("area", "").strip()
                time_slot = row.get("time_slot", "").strip()
                
                if area not in valid_areas:
                    # In a real app we might relax this or allow adding new areas dynamically. 
                    # For now, strict validation as requested.
                    return False, f"Row {line_num}: Unknown area '{area}'"
                
                if not time_pattern.match(time_slot):
                    return False, f"Row {line_num}: Invalid time format '{time_slot}'. Expected HH:MM - HH:MM"
                    
    except Exception as e:
        return False, f"Error reading CSV: {e}"

    return True, None

def calculate_daily_outage_hours(area):
    """Calcs total hours per day for a given area based on schedule slots."""
    schedule = load_schedule_from_db(area)
    total_hours = 0.0
    for slot in schedule:
        try:
            start_str, end_str = slot.split(" - ")
            start_dt = datetime.strptime(start_str, "%H:%M")
            end_dt = datetime.strptime(end_str, "%H:%M")
            
            diff = (end_dt - start_dt).seconds / 3600
            if diff < 0: diff += 24 # Handle wrap around if needed, though usually dealt with in delta
            total_hours += diff
        except ValueError:
            pass
    return total_hours

def get_analytics(area):
    now = datetime.now()
    
    # Time Ranges
    start_this_week = now - timedelta(days=now.weekday()) # Monday
    start_this_week = start_this_week.replace(hour=0, minute=0, second=0, microsecond=0)
    
    start_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    last_month_end = start_this_month - timedelta(seconds=1)
    start_last_month = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    daily_hours = calculate_daily_outage_hours(area)
    
    def calculate_hours_in_range(start_date, end_date):
        total = 0
        current = start_date
        while current <= end_date:
            # Find stage active on 'current' day
            # Get last stage change before end of 'current' day
            day_end_str = current.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT stage FROM stage_history WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (day_end_str,))
            res = cursor.fetchone()
            stage = res[0] if res else 0
            
            if stage > 0:
                total += daily_hours
            
            current += timedelta(days=1)
        return total

    return {
        "this_week": calculate_hours_in_range(start_this_week, now),
        "this_month": calculate_hours_in_range(start_this_month, now),
        "last_month": calculate_hours_in_range(start_last_month, last_month_end)
    }

def calculate_next_outage(schedule_slots):
    """
    Returns (state, hours, minutes, seconds_diff, next_start_dt)
    state: "ACTIVE", "FUTURE", "NONE"
    """
    if not schedule_slots or schedule_slots == ["No schedule available for this area"]:
        return "NONE", 0, 0, 0, None
        
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    tomorrow = now + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    
    upcoming_diffs = []
    current_active = None

    for slot in schedule_slots:
        try:
            start_str, end_str = slot.split(" - ")
            
            # Create datetime objects for today
            start_dt = datetime.strptime(f"{today_str} {start_str}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{today_str} {end_str}", "%Y-%m-%d %H:%M")
            
            # Handle "Current" outage wrap-around (e.g. 22:00 - 00:30)
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
                
            if start_dt <= now < end_dt:
                time_left = end_dt - now
                hours, remainder = divmod(time_left.seconds, 3600)
                minutes = remainder // 60
                return "ACTIVE", hours, minutes, time_left.total_seconds(), start_dt

            # Handle "Future" outage (Today)
            if start_dt > now:
                upcoming_diffs.append((start_dt - now, start_dt))
            
            # Handle "Tomorrow" (Recurrence)
            start_dt_tom = datetime.strptime(f"{tomorrow_str} {start_str}", "%Y-%m-%d %H:%M")
            upcoming_diffs.append((start_dt_tom - now, start_dt_tom))
            
        except ValueError:
            continue
            
    if not upcoming_diffs:
        return "NONE", 0, 0, 0, None
        
    # Find smallest positive diff
    upcoming_diffs.sort()
    diff, next_dt = upcoming_diffs[0]
    
    hours, remainder = divmod(diff.seconds, 3600)
    minutes = remainder // 60
    hours += diff.days * 24
    
    return "FUTURE", hours, minutes, diff.total_seconds(), next_dt
