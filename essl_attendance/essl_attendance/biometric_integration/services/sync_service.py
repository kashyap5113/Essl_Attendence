import frappe
from frappe.utils import now_datetime
from essl_attendance.biometric_integration.services.mapping_service import MappingService
from essl_attendance.biometric_integration.services.checkin_service import CheckinService


def sync_all_devices():
    """Scheduler entry point: sync all enabled devices that use polling.
    Called by the cron job defined in hooks.py.
    Only processes TCP/IP and Dummy devices (ADMS Push devices handle themselves).
    """
    devices = frappe.get_all(
        "Biometric Device",
        filters={
            "enabled": 1,
            "auto_sync": 1,
            "communication_type": ["in", ["TCP/IP (LAN Only)", "Dummy Data (Testing)"]]
        },
        pluck="name"
    )
    for device_name in devices:
        try:
            sync_device(device_name)
        except Exception as e:
            frappe.log_error(
                title=f"Sync Error: {device_name}",
                message=str(e)
            )


def sync_device(device_name, sync_type="Poll"):
    """Sync attendance data from a single device using TCP/IP polling.
    
    Args:
        device_name: Name of the Biometric Device document
        sync_type: "Poll" (scheduled), "Manual" (user-triggered)
        
    Returns:
        dict with sync results
    """
    device = frappe.get_doc("Biometric Device", device_name)

    # Prevent concurrent syncs using a simple Redis lock
    lock_key = f"biometric_sync_{device_name}"
    if not frappe.cache.set_value(lock_key, 1, expires_in_sec=300):
        # Lock already held — check if it's a real lock
        if frappe.cache.get_value(lock_key):
            return {"status": "Failed", "error": "Sync already in progress for this device"}

    try:
        frappe.cache.set_value(lock_key, 1, expires_in_sec=300)
        return _do_sync(device, sync_type)
    finally:
        frappe.cache.delete_value(lock_key)


def _do_sync(device, sync_type):
    """Internal sync logic — performs the actual data fetch and processing."""
    # Initialize sync log
    log = frappe.new_doc("Biometric Sync Log")
    log.device = device.name
    log.sync_type = sync_type
    log.status = "Started"
    log.start_time = now_datetime()
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    # Get the appropriate client
    client = _get_client(device)
    if not client:
        log.status = "Failed"
        log.error_message = f"Unsupported communication type: {device.communication_type}"
        log.end_time = now_datetime()
        log.save(ignore_permissions=True)
        device.update_last_sync(success=False, error_message=log.error_message)
        frappe.db.commit()
        return {"status": "Failed", "error": log.error_message}

    # Connect to device
    if not client.connect():
        log.status = "Failed"
        log.error_message = "Could not connect to device"
        log.end_time = now_datetime()
        log.save(ignore_permissions=True)
        device.update_last_sync(success=False, error_message=log.error_message)
        frappe.db.commit()
        return {"status": "Failed", "error": log.error_message}

    try:
        attendance = client.get_attendance()
        if attendance is None:
            attendance = []

        log.fetched_count = len(attendance)

        created = 0
        duplicates = 0
        unmapped = 0
        failed = 0
        errors = []

        for record in attendance:
            user_id = str(record.get("user_id", "")).strip()
            timestamp = record.get("timestamp")
            punch_type = str(record.get("punch_type", ""))

            if not user_id or not timestamp:
                failed += 1
                errors.append(f"Missing user_id or timestamp in record")
                continue

            # Store raw punch (idempotent via idempotency_key unique constraint)
            try:
                raw = frappe.new_doc("Biometric Raw Punch")
                raw.device = device.name
                raw.device_user_id = user_id
                raw.punch_time = timestamp
                raw.punch_type = punch_type
                raw.source_type = "Poll"
                raw.received_at = now_datetime()
                raw.processing_status = "Pending"
                raw.insert(ignore_permissions=True)
            except frappe.DuplicateEntryError:
                duplicates += 1
                frappe.clear_last_message()
                continue
            except Exception as e:
                failed += 1
                errors.append(f"Error storing punch for user {user_id}: {str(e)[:100]}")
                continue

            # Map user to employee
            employee = MappingService.get_employee_for_biometric_user(device.name, user_id)
            if not employee:
                unmapped += 1
                raw.mark_unmapped()
                continue

            # Create Employee Checkin
            success, checkin_name, error = CheckinService.create_employee_checkin(
                employee=employee,
                punch_time=timestamp,
                device_id=device.name,
                punch_type=punch_type,
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

        # Disconnect
        client.disconnect()

        # Determine status
        if failed == 0 and unmapped == 0:
            log.status = "Success"
        elif created > 0:
            log.status = "Partial Success"
        elif len(attendance) == 0 or (duplicates > 0 and failed == 0 and unmapped == 0):
            log.status = "Success"
        else:
            log.status = "Failed" if created == 0 else "Partial Success"

        log.created_count = created
        log.duplicate_count = duplicates
        log.unmapped_count = unmapped
        log.failed_count = failed
        log.end_time = now_datetime()
        log.error_message = "; ".join(errors[:5]) if errors else ""
        log.error_details = "\n".join(errors[:50]) if errors else ""
        log.save(ignore_permissions=True)

        device.update_last_sync(
            success=(log.status in ["Success", "Partial Success"]),
            error_message=log.error_message
        )
        frappe.db.commit()

        return {
            "status": log.status,
            "created": created,
            "duplicates": duplicates,
            "unmapped": unmapped,
            "failed": failed
        }

    except Exception as e:
        client.disconnect()
        log.status = "Failed"
        log.error_message = str(e)[:500]
        log.end_time = now_datetime()
        log.save(ignore_permissions=True)
        device.update_last_sync(success=False, error_message=str(e))
        frappe.db.commit()
        frappe.log_error(title=f"Sync Error: {device.name}", message=str(e))
        return {"status": "Failed", "error": str(e)}


def _get_client(device):
    """Create the appropriate client based on device communication type."""
    if device.communication_type == "Dummy Data (Testing)":
        from essl_attendance.biometric_integration.clients.dummy_client import DummyClient
        return DummyClient(ip_address="127.0.0.1", port=4370)

    elif device.communication_type == "TCP/IP (LAN Only)":
        try:
            from essl_attendance.biometric_integration.clients.k90_client import K90Client
        except ImportError:
            frappe.log_error(
                title="pyzk not installed",
                message="The 'pyzk' package is required for TCP/IP mode. "
                        "Install it with: pip install pyzk"
            )
            return None
        password = device.get_password("connection_password") if device.connection_password else None
        return K90Client(
            ip_address=device.ip_address,
            port=device.port or 4370,
            password=password
        )

    return None


def reprocess_failed_punches(device_name):
    """Reprocess punches that failed or were unmapped.
    
    Called after fixing user mappings or resolving errors.
    Returns dict with results.
    """
    punches = frappe.get_all(
        "Biometric Raw Punch",
        filters={
            "device": device_name,
            "processing_status": ["in", ["Failed", "Unmapped", "Pending"]]
        },
        pluck="name",
        limit=500
    )

    if not punches:
        return {"processed": 0, "failed": 0}

    # Create sync log for reprocessing
    log = frappe.new_doc("Biometric Sync Log")
    log.device = device_name
    log.sync_type = "Reprocess"
    log.status = "Started"
    log.start_time = now_datetime()
    log.fetched_count = len(punches)
    log.insert(ignore_permissions=True)

    processed = 0
    still_failed = 0

    for punch_name in punches:
        try:
            raw = frappe.get_doc("Biometric Raw Punch", punch_name)
            if raw.retry_processing():
                processed += 1
            else:
                still_failed += 1
        except Exception as e:
            still_failed += 1
            frappe.log_error(
                title="Reprocess Error",
                message=f"Punch: {punch_name}, Error: {str(e)}"
            )

    log.created_count = processed
    log.failed_count = still_failed
    log.status = "Success" if still_failed == 0 else "Partial Success"
    log.end_time = now_datetime()
    log.save(ignore_permissions=True)
    frappe.db.commit()

    return {"processed": processed, "failed": still_failed}
