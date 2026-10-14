"""
iClock / ADMS Push Protocol Handler for eSSL/ZKTeco Biometric Devices

This module implements the server-side endpoints for the ZKTeco ADMS (iClock) push protocol.
The biometric device initiates HTTP requests to these endpoints to:
  - Register/handshake (GET /iclock/cdata)
  - Upload attendance logs (POST /iclock/cdata)
  - Poll for commands / heartbeat (GET /iclock/getrequest)
  - Report command execution (POST /iclock/devicecmd)

These endpoints are mapped via Nginx rewrite rules:
  /iclock/cdata      -> /api/method/essl_attendance.iclock.cdata
  /iclock/getrequest -> /api/method/essl_attendance.iclock.getrequest
  /iclock/devicecmd  -> /api/method/essl_attendance.iclock.devicecmd

All endpoints use allow_guest=True because the device sends unauthenticated HTTP.
Security is provided by serial number validation + rate limiting.
"""

import frappe
from frappe.utils import now_datetime, cstr
from werkzeug.wrappers import Response
import hashlib
import time

# ─── Simple in-memory rate limiter ───────────────────────────────────────────
_rate_limit_store = {}
RATE_LIMIT_MAX = 200  # max requests per window
RATE_LIMIT_WINDOW = 60  # seconds


def _check_rate_limit(ip):
    """Return True if the request should be allowed, False if rate-limited."""
    now = time.time()
    key = ip
    if key in _rate_limit_store:
        count, window_start = _rate_limit_store[key]
        if now - window_start > RATE_LIMIT_WINDOW:
            _rate_limit_store[key] = (1, now)
            return True
        if count >= RATE_LIMIT_MAX:
            return False
        _rate_limit_store[key] = (count + 1, window_start)
        return True
    else:
        _rate_limit_store[key] = (1, now)
        return True


def _plain_response(text, status=200):
    """Return a plain text HTTP response (what the device firmware expects)."""
    return Response(cstr(text), status=status, content_type="text/plain")


def _get_serial_number():
    """Extract the device serial number from the request query parameters."""
    return frappe.local.form_dict.get("SN", "").strip()


def _get_device(serial_number):
    """Look up a Biometric Device by serial number. Returns (name, doc) or (None, None)."""
    if not serial_number:
        return None, None
    device_name = frappe.db.get_value(
        "Biometric Device",
        {"serial_number": serial_number, "enabled": 1},
        "name"
    )
    if not device_name:
        return None, None
    return device_name, frappe.get_doc("Biometric Device", device_name)


# ═══════════════════════════════════════════════════════════════════════════════
#  /iclock/cdata — Handshake (GET) and Data Upload (POST)
# ═══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def cdata():
    """Handle both GET (handshake) and POST (attendance data upload) for /iclock/cdata."""
    ip = frappe.local.request_ip
    if not _check_rate_limit(ip):
        return _plain_response("ERROR: Rate limited", 429)

    sn = _get_serial_number()
    if not sn:
        return _plain_response("ERROR", 400)

    if frappe.request.method == "GET":
        return _handle_handshake(sn)
    elif frappe.request.method == "POST":
        return _handle_data_upload(sn)
    else:
        return _plain_response("ERROR", 405)


def _handle_handshake(sn):
    """Handle GET /iclock/cdata — device registration/handshake.
    
    The device sends this when it boots up or reconnects.
    Server responds with configuration parameters and stamp values.
    """
    device_name, device = _get_device(sn)

    if not device:
        # Unknown device — log for admin visibility but don't reveal details to caller
        frappe.logger("iclock").warning(f"Handshake from unknown/disabled device SN: {sn}")
        # Still return OK-ish response so device doesn't flood retries,
        # but with empty config
        return _plain_response("OK")

    # Update heartbeat
    device.update_heartbeat()
    frappe.db.commit()

    # Read current stamps from device record
    attlog_stamp = device.attlog_stamp or "0"
    operlog_stamp = device.operlog_stamp or "0"

    # Build response — tells the device what data to send and how often to poll
    response_lines = [
        f"GET OPTION FROM: {sn}",
        f"ATTLOGStamp={attlog_stamp}",
        f"OPERLOGStamp={operlog_stamp}",
        "ErrorDelay=30",
        "Delay=10",
        "TransTimes=00:00;23:59",
        "TransInterval=1",
        "TransFlag=1111000000",
        f"ServerVer=1.0.0",
        "Realtime=1",
    ]
    return _plain_response("\r\n".join(response_lines))


def _handle_data_upload(sn):
    """Handle POST /iclock/cdata — attendance log / operation log upload.
    
    The device sends tab-separated text data. Query param 'table' indicates
    the type: ATTLOG (attendance), OPERLOG (operations), etc.
    """
    device_name, device = _get_device(sn)
    if not device:
        frappe.logger("iclock").warning(f"Data upload from unknown/disabled device SN: {sn}")
        return _plain_response("OK")

    # Update heartbeat
    device.update_heartbeat()

    table = frappe.local.form_dict.get("table", "").upper()
    stamp = frappe.local.form_dict.get("Stamp", "")

    # Read request body
    try:
        data = frappe.request.get_data(as_text=True)
    except Exception:
        data = ""

    if not data or not data.strip():
        frappe.db.commit()
        return _plain_response("OK")

    # Limit payload size (1MB max)
    if len(data) > 1_048_576:
        frappe.logger("iclock").error(f"Payload too large from SN={sn}: {len(data)} bytes")
        frappe.db.commit()
        return _plain_response("OK")

    if table == "ATTLOG":
        count = _process_attlog(device_name, device, data)
        # Update stamp
        if stamp:
            frappe.db.set_value("Biometric Device", device_name,
                              "attlog_stamp", stamp, update_modified=False)
        frappe.db.commit()
        return _plain_response(f"OK: {count}")

    elif table == "OPERLOG":
        # Operation logs — store but don't process as attendance
        if stamp:
            frappe.db.set_value("Biometric Device", device_name,
                              "operlog_stamp", stamp, update_modified=False)
        frappe.db.commit()
        return _plain_response("OK")

    else:
        # Unknown table or no table specified — try parsing as ATTLOG
        count = _process_attlog(device_name, device, data)
        frappe.db.commit()
        return _plain_response(f"OK: {count}")


def _process_attlog(device_name, device, data):
    """Parse and store ATTLOG (attendance log) data from the device.
    
    ATTLOG format (tab-separated):
        UserPIN\tTimestamp\tStatus\tVerifyMode\tWorkCode\tReserved1\tReserved2
    
    Example:
        101\t2026-10-14 08:30:12\t0\t1\t0\t0\t0
        
    Status field: 0=Check-In, 1=Check-Out, 2=Break-Out, 3=Break-In, 4=OT-In, 5=OT-Out
    """
    lines = data.strip().split("\n")
    stored_count = 0

    # Create sync log for this push batch
    sync_log = frappe.new_doc("Biometric Sync Log")
    sync_log.device = device_name
    sync_log.sync_type = "Push"
    sync_log.status = "Started"
    sync_log.start_time = now_datetime()
    sync_log.fetched_count = len([l for l in lines if l.strip()])
    sync_log.insert(ignore_permissions=True)

    created = 0
    duplicates = 0
    unmapped = 0
    failed = 0
    errors = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            failed += 1
            errors.append(f"Malformed line (too few fields): {line[:80]}")
            continue

        user_id = parts[0].strip()
        timestamp_str = parts[1].strip()
        # Status field (punch direction): 0=IN, 1=OUT, etc.
        punch_status = parts[2].strip() if len(parts) > 2 else ""
        verify_mode = parts[3].strip() if len(parts) > 3 else ""

        # Validate timestamp format
        if not _is_valid_timestamp(timestamp_str):
            failed += 1
            errors.append(f"Invalid timestamp for user {user_id}: {timestamp_str[:30]}")
            continue

        # Generate idempotency key
        idemp_key = hashlib.sha256(
            f"{device_name}|{user_id}|{timestamp_str}|{punch_status}".encode()
        ).hexdigest()[:40]

        # Check if already stored (fast path)
        if frappe.db.exists("Biometric Raw Punch", {"idempotency_key": idemp_key}):
            duplicates += 1
            continue

        # Store raw punch
        try:
            raw = frappe.new_doc("Biometric Raw Punch")
            raw.device = device_name
            raw.device_user_id = user_id
            raw.punch_time = timestamp_str
            raw.punch_type = punch_status
            raw.source_type = "Push"
            raw.received_at = now_datetime()
            raw.raw_payload = line[:500]
            raw.idempotency_key = idemp_key
            raw.processing_status = "Pending"
            raw.insert(ignore_permissions=True)
            stored_count += 1
        except frappe.DuplicateEntryError:
            duplicates += 1
            frappe.clear_last_message()
            continue
        except Exception as e:
            failed += 1
            errors.append(f"Error storing punch for user {user_id}: {str(e)[:100]}")
            frappe.log_error(
                title="iClock Raw Punch Storage Error",
                message=f"Device: {device_name}, User: {user_id}, Error: {str(e)}"
            )
            continue

        # Process punch → Employee Checkin
        try:
            from essl_attendance.biometric_integration.services.mapping_service import MappingService
            from essl_attendance.biometric_integration.services.checkin_service import CheckinService

            employee = MappingService.get_employee_for_biometric_user(device_name, user_id)
            if not employee:
                unmapped += 1
                raw.mark_unmapped()
                continue

            success, checkin_name, error = CheckinService.create_employee_checkin(
                employee=employee,
                punch_time=timestamp_str,
                device_id=device_name,
                punch_type=punch_status,
                device_timezone=device.device_timezone
            )
            if success:
                created += 1
                raw.mark_processed(checkin_name)
            else:
                if "Duplicate" in str(error):
                    duplicates += 1
                    raw.processing_status = "Processed"
                    raw.processed = 1
                    raw.error_message = "Checkin already exists"
                    raw.save(ignore_permissions=True)
                else:
                    failed += 1
                    raw.mark_failed(error)
                    errors.append(f"Checkin failed for user {user_id}: {error}")

        except Exception as e:
            failed += 1
            raw.mark_failed(str(e))
            errors.append(f"Processing error for user {user_id}: {str(e)[:100]}")

    # Finalize sync log
    sync_log.created_count = created
    sync_log.duplicate_count = duplicates
    sync_log.unmapped_count = unmapped
    sync_log.failed_count = failed
    sync_log.end_time = now_datetime()

    if failed == 0 and unmapped == 0:
        sync_log.status = "Success"
    elif created > 0:
        sync_log.status = "Partial Success"
    elif stored_count == 0 and duplicates > 0 and failed == 0:
        sync_log.status = "Success"  # All duplicates = already synced
    else:
        sync_log.status = "Failed" if created == 0 and stored_count == 0 else "Partial Success"

    sync_log.error_message = "; ".join(errors[:5]) if errors else ""
    sync_log.error_details = "\n".join(errors[:50]) if errors else ""
    sync_log.save(ignore_permissions=True)

    # Update device last sync
    device.update_last_sync(
        success=(sync_log.status in ["Success", "Partial Success"]),
        error_message=sync_log.error_message
    )

    return stored_count


def _is_valid_timestamp(ts):
    """Basic validation that the timestamp looks like YYYY-MM-DD HH:MM:SS."""
    if not ts or len(ts) < 10:
        return False
    try:
        # Check basic format
        parts = ts.split(" ")
        if len(parts) < 2:
            return False
        date_parts = parts[0].split("-")
        if len(date_parts) != 3:
            return False
        year = int(date_parts[0])
        month = int(date_parts[1])
        day = int(date_parts[2])
        if year < 2000 or year > 2100 or month < 1 or month > 12 or day < 1 or day > 31:
            return False
        return True
    except (ValueError, IndexError):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  /iclock/getrequest — Heartbeat / Command Polling
# ═══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True, methods=["GET"])
def getrequest():
    """Handle GET /iclock/getrequest — device heartbeat and command polling.
    
    The device calls this periodically (based on the Delay value from handshake).
    Server responds with 'OK' if no commands, or command strings if pending.
    """
    ip = frappe.local.request_ip
    if not _check_rate_limit(ip):
        return _plain_response("OK", 429)

    sn = _get_serial_number()
    if not sn:
        return _plain_response("OK")

    device_name, device = _get_device(sn)
    if device:
        device.update_heartbeat()
        frappe.db.commit()

    # No command queuing implemented yet — just acknowledge
    return _plain_response("OK")


# ═══════════════════════════════════════════════════════════════════════════════
#  /iclock/devicecmd — Command Execution Feedback
# ═══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True, methods=["POST"])
def devicecmd():
    """Handle POST /iclock/devicecmd — device reports command execution results.
    
    The device posts back after executing a command received from getrequest.
    """
    ip = frappe.local.request_ip
    if not _check_rate_limit(ip):
        return _plain_response("OK", 429)

    sn = _get_serial_number()
    if not sn:
        return _plain_response("OK")

    device_name, device = _get_device(sn)
    if device:
        device.update_heartbeat()
        frappe.db.commit()

    # Log the command result for debugging
    try:
        data = frappe.request.get_data(as_text=True)
        if data:
            frappe.logger("iclock").info(f"Device command result from SN={sn}: {data[:200]}")
    except Exception:
        pass

    return _plain_response("OK")
