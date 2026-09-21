import frappe
from frappe.utils import now_datetime
from essl_attendance.biometric_integration.services.mapping_service import MappingService
from essl_attendance.biometric_integration.services.checkin_service import CheckinService
from werkzeug.wrappers import Response

@frappe.whitelist(allow_guest=True)
def receive_punch():
    """
    Standard ADMS Push endpoint for ZKTeco/eSSL devices.
    The device sends HTTP POST data to this URL.
    Usually the serial number is in the query params (e.g., ?SN=12345)
    and the payload contains the punch data.
    """
    sn = frappe.local.form_dict.get('SN')
    if not sn:
        return Response("ERROR: Missing SN", status=400, mimetype='text/plain')

    # Find device by SN
    device_name = frappe.db.get_value("Biometric Device", {"serial_number": sn, "enabled": 1}, "name")
    if not device_name:
        return Response("ERROR: Unknown Device", status=403, mimetype='text/plain')

    # The punch data is usually in the raw body
    data = frappe.request.get_data(as_text=True)
    if not data:
        return Response("OK", status=200, mimetype='text/plain')
        
    lines = data.strip().split('\n')
    
    created = 0
    for line in lines:
        if not line.strip(): continue
        # Example ADMS line: USERID\tTIMESTAMP\tPUNCHTYPE...
        # "10025\t2026-09-21 10:00:00\t0\t1\t0\t0"
        parts = line.strip().split('\t')
        if len(parts) >= 2:
            user_id = parts[0]
            timestamp = parts[1]
            punch_type = parts[2] if len(parts) > 2 else "0"
            
            # Idempotency check via Raw Punch insertion
            try:
                raw = frappe.new_doc("Biometric Raw Punch")
                raw.device = device_name
                raw.device_user_id = user_id
                raw.punch_time = timestamp
                raw.punch_type = punch_type
                raw.insert(ignore_permissions=True)
                frappe.db.commit()
            except frappe.DuplicateEntryError:
                continue # Skip processing if duplicate
                
            # Map Biometric User to Employee
            employee = MappingService.get_employee_for_biometric_user(device_name, user_id)
            if employee:
                success = CheckinService.create_employee_checkin(
                    employee=employee,
                    punch_time=timestamp,
                    device_id=device_name,
                    punch_type=punch_type
                )
                if success:
                    raw.processed = 1
                    raw.save(ignore_permissions=True)
                    frappe.db.commit()
                    created += 1
            else:
                raw.error_message = "User not mapped"
                raw.save(ignore_permissions=True)
                frappe.db.commit()

    # The machine expects a simple "OK" to confirm receipt
    return Response("OK", status=200, mimetype='text/plain')

# The machine may also ping getrequest to fetch commands (like setting time)
@frappe.whitelist(allow_guest=True)
def getrequest():
    return Response("OK", status=200, mimetype='text/plain')
