"""
Admin API endpoints for eSSL Attendance.
All methods here require authentication (no allow_guest).
"""

import frappe


@frappe.whitelist()
def test_device_connection(device_name):
    """Test TCP/IP connection to a biometric device.
    Only works for TCP/IP (LAN Only) devices.
    """
    frappe.has_permission("Biometric Device", "read", throw=True)

    device = frappe.get_doc("Biometric Device", device_name)
    if device.communication_type != "TCP/IP (LAN Only)":
        return {"success": False, "error": "Test connection only works for TCP/IP devices"}

    try:
        from essl_attendance.biometric_integration.clients.k90_client import K90Client
        password = device.get_password("connection_password") if device.connection_password else None
        client = K90Client(
            ip_address=device.ip_address,
            port=device.port or 4370,
            password=password
        )
        if client.test_connection():
            device.update_heartbeat()
            frappe.db.commit()
            return {"success": True}
        else:
            return {"success": False, "error": "Could not connect to device"}
    except ImportError:
        return {"success": False, "error": "pyzk package not installed. Run: pip install pyzk"}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


@frappe.whitelist()
def manual_sync(device_name):
    """Manually trigger a sync for a polling-based device."""
    frappe.has_permission("Biometric Device", "write", throw=True)

    device = frappe.get_doc("Biometric Device", device_name)
    if device.communication_type == "ADMS Push":
        return {"status": "Failed", "error": "ADMS Push devices sync automatically. No manual sync needed."}

    if not device.enabled:
        return {"status": "Failed", "error": "Device is disabled"}

    from essl_attendance.biometric_integration.services.sync_service import sync_device
    result = sync_device(device_name, sync_type="Manual")
    return result


@frappe.whitelist()
def reprocess_failed_punches(device_name):
    """Reprocess punches that were unmapped or failed."""
    frappe.has_permission("Biometric Device", "write", throw=True)

    if not frappe.db.exists("Biometric Device", device_name):
        frappe.throw(f"Device '{device_name}' not found")

    from essl_attendance.biometric_integration.services.sync_service import reprocess_failed_punches as _reprocess
    result = _reprocess(device_name)
    return result


@frappe.whitelist()
def get_device_status(device_name):
    """Get current status of a biometric device."""
    frappe.has_permission("Biometric Device", "read", throw=True)

    device = frappe.get_doc("Biometric Device", device_name)
    return {
        "connection_status": device.connection_status,
        "last_heartbeat": str(device.last_heartbeat) if device.last_heartbeat else None,
        "last_sync": str(device.last_sync) if device.last_sync else None,
        "last_successful_sync": str(device.last_successful_sync) if device.last_successful_sync else None,
        "last_error": device.last_error,
        "communication_type": device.communication_type
    }


@frappe.whitelist()
def get_unmapped_users(device_name):
    """Get list of device user IDs that have no employee mapping."""
    frappe.has_permission("Biometric User Mapping", "read", throw=True)

    from essl_attendance.biometric_integration.services.mapping_service import MappingService
    return MappingService.get_unmapped_user_ids(device_name)
