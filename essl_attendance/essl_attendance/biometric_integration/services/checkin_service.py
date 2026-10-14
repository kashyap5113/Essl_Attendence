import frappe
from frappe.utils import now_datetime, get_datetime
from datetime import datetime


class CheckinService:
    """Service for creating Employee Checkin records from biometric punches."""

    @staticmethod
    def create_employee_checkin(employee, punch_time, device_id, punch_type=None,
                                 device_timezone=None):
        """Create an Employee Checkin record.
        
        Returns:
            tuple: (success: bool, checkin_name: str or None, error: str or None)
        """
        try:
            # Validate employee exists and is active
            emp_status = frappe.db.get_value("Employee", employee, "status")
            if not emp_status:
                return False, None, f"Employee '{employee}' not found"
            if emp_status != "Active":
                return False, None, f"Employee '{employee}' is not active (status: {emp_status})"

            # Normalize timestamp
            punch_dt = CheckinService._normalize_timestamp(punch_time, device_timezone)
            if not punch_dt:
                return False, None, f"Invalid timestamp: {punch_time}"

            # Validate timestamp is not unreasonably in the future or past
            now = now_datetime()
            if punch_dt > now_datetime():
                # Allow up to 5 minutes in the future (clock drift tolerance)
                from frappe.utils import time_diff_in_seconds
                diff = time_diff_in_seconds(punch_dt, now)
                if diff > 300:
                    return False, None, f"Timestamp is {int(diff)}s in the future"

            # Check for duplicate Employee Checkin
            exists = frappe.db.exists("Employee Checkin", {
                "employee": employee,
                "time": punch_dt
            })
            if exists:
                return False, None, "Duplicate: Employee Checkin already exists for this time"

            # Create the checkin
            doc = frappe.new_doc("Employee Checkin")
            doc.employee = employee
            doc.time = punch_dt
            doc.device_id = device_id

            # Map punch type to log_type
            log_type = CheckinService._map_punch_type(punch_type)
            if log_type:
                doc.log_type = log_type

            doc.insert(ignore_permissions=True)
            return True, doc.name, None

        except frappe.DuplicateEntryError:
            return False, None, "Duplicate: Employee Checkin already exists"
        except Exception as e:
            frappe.log_error(
                title="Biometric Checkin Error",
                message=f"Employee: {employee}, Time: {punch_time}, Error: {str(e)}"
            )
            return False, None, str(e)

    @staticmethod
    def _normalize_timestamp(punch_time, device_timezone=None):
        """Convert punch_time to a proper datetime, applying timezone if needed.
        
        The device reports time in its local timezone. If device_timezone differs
        from the server timezone, we need to convert.
        """
        try:
            if isinstance(punch_time, str):
                # Parse the timestamp string
                dt = get_datetime(punch_time)
            elif isinstance(punch_time, datetime):
                dt = punch_time
            else:
                return None

            # If device timezone is specified and differs from system timezone,
            # convert the timestamp
            if device_timezone:
                try:
                    import pytz
                    system_tz = frappe.utils.get_system_timezone()
                    if device_timezone != system_tz:
                        device_tz = pytz.timezone(device_timezone)
                        system_tz_obj = pytz.timezone(system_tz)
                        # The punch_time is in device's local time (naive)
                        localized = device_tz.localize(dt)
                        # Convert to system timezone
                        dt = localized.astimezone(system_tz_obj).replace(tzinfo=None)
                except Exception:
                    # If timezone conversion fails, use the timestamp as-is
                    # This is safer than failing silently
                    pass

            return dt
        except Exception:
            return None

    @staticmethod
    def _map_punch_type(punch_type):
        """Map device punch type code to HRMS log_type.
        
        Standard eSSL/ZKTeco status codes:
            0 = Check-In
            1 = Check-Out
            2 = Break-Out
            3 = Break-In
            4 = OT-In
            5 = OT-Out
        
        HRMS Employee Checkin log_type is typically left empty
        to let Auto Attendance determine IN/OUT based on shift.
        If the device provides a clear IN/OUT signal, we use it.
        """
        if punch_type is None or punch_type == "":
            return None

        punch_str = str(punch_type).strip()
        mapping = {
            "0": "IN",     # Check-In
            "1": "OUT",    # Check-Out
            "4": "IN",     # OT-In
            "5": "OUT",    # OT-Out
        }
        return mapping.get(punch_str, None)
