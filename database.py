import gspread
from google.oauth2.service_account import Credentials
import datetime
import csv
from typing import List, Dict, Any, Optional

# --- Cached Google Sheets Connection ---
# We keep one persistent connection instead of re-authenticating on every call.
_client: Optional[gspread.Client] = None
_spreadsheet: Optional[gspread.Spreadsheet] = None
_ws_shifts: Optional[gspread.Worksheet] = None
_ws_settings: Optional[gspread.Worksheet] = None
_sheet_id: Optional[str] = None
_creds_path: Optional[str] = None

def _get_spreadsheet(sheet_id: str, credentials_path: str) -> gspread.Spreadsheet:
    """Return cached spreadsheet, or connect and cache if not yet connected."""
    global _client, _spreadsheet, _sheet_id, _creds_path
    if _spreadsheet is not None and _sheet_id == sheet_id:
        return _spreadsheet
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        _client = gspread.authorize(creds)
        _spreadsheet = _client.open_by_key(sheet_id)
        _sheet_id = sheet_id
        _creds_path = credentials_path
        return _spreadsheet
    except Exception as e:
        raise ConnectionError(f"ไม่สามารถเชื่อมต่อ Google Sheet ได้: {str(e)}")

def _get_ws_shifts(sheet_id: str, credentials_path: str) -> gspread.Worksheet:
    """Return cached shifts worksheet."""
    global _ws_shifts
    if _ws_shifts is not None and _sheet_id == sheet_id:
        return _ws_shifts
    sp = _get_spreadsheet(sheet_id, credentials_path)
    _ws_shifts = sp.worksheet("shifts")
    return _ws_shifts

def _get_ws_settings(sheet_id: str, credentials_path: str) -> gspread.Worksheet:
    """Return cached settings worksheet."""
    global _ws_settings
    if _ws_settings is not None and _sheet_id == sheet_id:
        return _ws_settings
    sp = _get_spreadsheet(sheet_id, credentials_path)
    _ws_settings = sp.worksheet("settings")
    return _ws_settings

def invalidate_cache() -> None:
    """Reset the cached connection (call if a gspread APIError occurs)."""
    global _client, _spreadsheet, _ws_shifts, _ws_settings, _sheet_id, _creds_path
    _client = None
    _spreadsheet = None
    _ws_shifts = None
    _ws_settings = None
    _sheet_id = None
    _creds_path = None

def _safe_call(fn, *args, **kwargs):
    """
    Retry helper: if the first call raises a gspread APIError (e.g. token expired),
    invalidate the cache and try once more with a fresh connection.
    """
    try:
        return fn(*args, **kwargs)
    except gspread.exceptions.APIError:
        invalidate_cache()
        return fn(*args, **kwargs)

# --- Initialization ---

def init_db(sheet_id: str, credentials_path: str) -> None:
    """Ensure 'shifts' and 'settings' worksheets exist in the spreadsheet."""
    sp = _get_spreadsheet(sheet_id, credentials_path)
    existing = [ws.title for ws in sp.worksheets()]

    global _ws_shifts, _ws_settings

    if "shifts" not in existing:
        _ws_shifts = sp.add_worksheet(title="shifts", rows="1000", cols="6")
        _ws_shifts.append_row(["Shift ID", "Discord User ID", "Username",
                                "Check In Time", "Check Out Time", "Duration (Hours)"])
        print("Created worksheet 'shifts'")
    else:
        _ws_shifts = sp.worksheet("shifts")

    if "settings" not in existing:
        _ws_settings = sp.add_worksheet(title="settings", rows="100", cols="2")
        _ws_settings.append_row(["Key", "Value"])
        print("Created worksheet 'settings'")
    else:
        _ws_settings = sp.worksheet("settings")

# --- Settings ---

def set_setting(key: str, value: str, sheet_id: str, credentials_path: str) -> None:
    """Save or update a setting in the 'settings' worksheet."""
    def _do():
        ws = _get_ws_settings(sheet_id, credentials_path)
        records = ws.get_all_records()
        for idx, record in enumerate(records, 2):
            if record.get("Key") == key:
                ws.update_cell(idx, 2, str(value))
                return
        ws.append_row([key, str(value)])

    _safe_call(_do)

def get_setting(key: str, sheet_id: str, credentials_path: str) -> Optional[str]:
    """Retrieve a setting value by key."""
    def _do():
        ws = _get_ws_settings(sheet_id, credentials_path)
        records = ws.get_all_records()
        for record in records:
            if record.get("Key") == key:
                return str(record.get("Value"))
        return None

    return _safe_call(_do)

# --- Shift Logging ---

def _all_shifts(sheet_id: str, credentials_path: str) -> List[Dict]:
    """Return all rows from the shifts worksheet as a list of dicts."""
    ws = _get_ws_shifts(sheet_id, credentials_path)
    return ws.get_all_records()

def get_active_shift_row(user_id: str, sheet_id: str, credentials_path: str) -> Optional[tuple[Dict, int]]:
    """Return (record, row_number) for the user's open shift, or None."""
    records = _all_shifts(sheet_id, credentials_path)
    for idx, record in enumerate(records, 2):
        if str(record.get("Discord User ID")) == str(user_id) and not record.get("Check Out Time"):
            return record, idx
    return None

def get_active_shift(user_id: str, sheet_id: str, credentials_path: str) -> Optional[Dict]:
    info = _safe_call(get_active_shift_row, user_id, sheet_id, credentials_path)
    return info[0] if info else None

def start_shift(user_id: str, username: str, sheet_id: str, credentials_path: str) -> str:
    """Start a new shift. Raises ValueError if already on shift."""
    def _do():
        info = get_active_shift_row(user_id, sheet_id, credentials_path)
        if info:
            raise ValueError("คุณกำลังอยู่ในเวรอยู่แล้ว (มีเวรที่ยังไม่ได้กดออก)")

        ws = _get_ws_shifts(sheet_id, credentials_path)
        records = ws.get_all_records()
        max_id = max((int(r.get("Shift ID", 0)) for r in records if str(r.get("Shift ID", "")).isdigit()), default=0)
        shift_id = max_id + 1

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([shift_id, str(user_id), username, now_str, "", ""])
        return now_str

    return _safe_call(_do)

def end_shift(user_id: str, sheet_id: str, credentials_path: str) -> Dict[str, Any]:
    """End the active shift. Raises ValueError if not on shift."""
    def _do():
        info = get_active_shift_row(user_id, sheet_id, credentials_path)
        if not info:
            raise ValueError("คุณยังไม่ได้เข้าเวร (ไม่พบเวรที่กำลังทำงานอยู่)")

        record, row_number = info
        check_in_str = record["Check In Time"]
        check_out_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            ci = datetime.datetime.strptime(check_in_str, "%Y-%m-%d %H:%M:%S")
            co = datetime.datetime.strptime(check_out_str, "%Y-%m-%d %H:%M:%S")
            duration_hours = round((co - ci).total_seconds() / 3600.0, 2)
        except Exception:
            duration_hours = 0.0

        ws = _get_ws_shifts(sheet_id, credentials_path)
        ws.update_cell(row_number, 5, check_out_str)
        ws.update_cell(row_number, 6, duration_hours)

        return {
            "id": record["Shift ID"],
            "user_id": user_id,
            "username": record["Username"],
            "check_in": check_in_str,
            "check_out": check_out_str,
            "duration_hours": duration_hours
        }

    return _safe_call(_do)

def get_currently_on_duty(sheet_id: str, credentials_path: str) -> List[Dict]:
    """Return list of users currently checked in."""
    def _do():
        records = _all_shifts(sheet_id, credentials_path)
        active = [
            {"user_id": str(r.get("Discord User ID")),
             "username": r.get("Username"),
             "check_in": r.get("Check In Time")}
            for r in records if not r.get("Check Out Time")
        ]
        active.sort(key=lambda x: x["check_in"])
        return active

    return _safe_call(_do)

def get_user_history(user_id: str, limit: int, sheet_id: str, credentials_path: str) -> List[Dict]:
    def _do():
        records = _all_shifts(sheet_id, credentials_path)
        user_shifts = [
            {"id": r.get("Shift ID"),
             "user_id": str(r.get("Discord User ID")),
             "username": r.get("Username"),
             "check_in": r.get("Check In Time"),
             "check_out": r.get("Check Out Time"),
             "duration_hours": float(r.get("Duration (Hours)")) if r.get("Duration (Hours)") else None}
            for r in records if str(r.get("Discord User ID")) == str(user_id)
        ]
        user_shifts.sort(key=lambda x: int(x["id"]) if str(x.get("id","")).isdigit() else 0, reverse=True)
        return user_shifts[:limit]

    return _safe_call(_do)

def get_user_total_hours(user_id: str, sheet_id: str, credentials_path: str) -> float:
    def _do():
        records = _all_shifts(sheet_id, credentials_path)
        total = sum(
            float(r.get("Duration (Hours)", 0) or 0)
            for r in records
            if str(r.get("Discord User ID")) == str(user_id) and r.get("Check Out Time")
        )
        return round(total, 2)

    return _safe_call(_do)

# --- Dashboard & Filter Queries ---

def get_date_range(filter_type: str) -> tuple[Optional[str], Optional[str], str]:
    now = datetime.datetime.now()
    if filter_type == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59)
        return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"), "วันนี้"
    elif filter_type == "week":
        start = (now - datetime.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59)
        return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"), "สัปดาห์นี้"
    elif filter_type == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59)
        return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"), "เดือนนี้"
    return None, None, "ทั้งหมด"

def _parse_dt(s: str) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def _in_range(check_in_str: str, start_dt, end_dt) -> bool:
    dt = _parse_dt(check_in_str)
    if not dt:
        return False
    if start_dt and dt < start_dt:
        return False
    if end_dt and dt > end_dt:
        return False
    return True

def get_shifts_stats(filter_type: str, sheet_id: str, credentials_path: str) -> Dict[str, Any]:
    """Get aggregated shift statistics for a time range. Uses a SINGLE Sheets API call."""
    def _do():
        start_str, end_str, label = get_date_range(filter_type)
        start_dt = _parse_dt(start_str) if start_str else None
        end_dt = _parse_dt(end_str) if end_str else None

        # Single call to fetch all rows
        records = _all_shifts(sheet_id, credentials_path)

        total_hours = 0.0
        total_shifts = 0
        unique_doctors = set()
        active_doctors = 0

        for r in records:
            check_out = r.get("Check Out Time")
            check_in_str = r.get("Check In Time", "")

            if not check_out:
                active_doctors += 1

            if check_out and _in_range(check_in_str, start_dt, end_dt):
                total_shifts += 1
                try:
                    total_hours += float(r.get("Duration (Hours)", 0) or 0)
                except (ValueError, TypeError):
                    pass
                unique_doctors.add(r.get("Discord User ID"))

        return {
            "total_hours": round(total_hours, 2),
            "total_shifts": total_shifts,
            "unique_doctors": len(unique_doctors),
            "active_doctors": active_doctors,
            "label": label
        }

    return _safe_call(_do)

def get_top_doctors_stats(filter_type: str, limit: int, sheet_id: str, credentials_path: str) -> List[Dict]:
    """Get doctors sorted by accumulated hours. Uses a SINGLE Sheets API call."""
    def _do():
        start_str, end_str, _ = get_date_range(filter_type)
        start_dt = _parse_dt(start_str) if start_str else None
        end_dt = _parse_dt(end_str) if end_str else None

        records = _all_shifts(sheet_id, credentials_path)
        doctor_data: Dict[str, Dict] = {}

        for r in records:
            user_id = str(r.get("Discord User ID"))
            check_out = r.get("Check Out Time")
            if check_out and _in_range(r.get("Check In Time", ""), start_dt, end_dt):
                try:
                    hours = float(r.get("Duration (Hours)", 0) or 0)
                except (ValueError, TypeError):
                    hours = 0.0
                if user_id not in doctor_data:
                    doctor_data[user_id] = {"user_id": user_id, "username": r.get("Username"), "total_hours": 0.0, "shift_count": 0}
                doctor_data[user_id]["username"] = r.get("Username")
                doctor_data[user_id]["total_hours"] += hours
                doctor_data[user_id]["shift_count"] += 1

        result = sorted(doctor_data.values(), key=lambda x: x["total_hours"], reverse=True)
        for d in result:
            d["total_hours"] = round(d["total_hours"], 2)
        return result[:limit]

    return _safe_call(_do)

def export_shifts_to_csv_by_filter(filter_type: str, sheet_id: str, credentials_path: str, output_filepath: str) -> None:
    """Export filtered shifts to a local CSV file."""
    def _do():
        start_str, end_str, _ = get_date_range(filter_type)
        start_dt = _parse_dt(start_str) if start_str else None
        end_dt = _parse_dt(end_str) if end_str else None

        records = _all_shifts(sheet_id, credentials_path)
        filtered = [r for r in records if not start_dt or _in_range(r.get("Check In Time", ""), start_dt, end_dt)]
        filtered.sort(key=lambda x: int(str(x.get("Shift ID", 0))) if str(x.get("Shift ID","")).isdigit() else 0, reverse=True)

        with open(output_filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["Shift ID", "Discord User ID", "Username", "Check In Time", "Check Out Time", "Duration (Hours)"])
            for r in filtered:
                writer.writerow([
                    r.get("Shift ID"), r.get("Discord User ID"), r.get("Username"),
                    r.get("Check In Time"),
                    r.get("Check Out Time") or "Active",
                    r.get("Duration (Hours)") or 0.0
                ])

    _safe_call(_do)
