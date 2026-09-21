import frappe
from frappe.utils import now_datetime
from essl_attendance.biometric_integration.clients.k90_client import K90Client
from essl_attendance.biometric_integration.services.mapping_service import MappingService
from essl_attendance.biometric_integration.services.checkin_service import CheckinService

def sync_all_devices():
    devices = frappe.get_all("Biometric Device", filters={"enabled": 1, "auto_sync": 1}, pluck="name")
    for device_name in devices:
        sync_device(device_name)

def sync_device(device_name):
    device = frappe.get_doc("Biometric Device", device_name)
    
    # Initialize Log
    log = frappe.new_doc("Biometric Sync Log")
    log.device = device.name
    log.status = "Started"
    log.start_time = now_datetime()
    log.insert(ignore_permissions=True)
    frappe.db.commit()
    
    if device.communication_type != "TCP/IP":
        log.status = "Failed"
        log.error_message = "Only TCP/IP Polling is currently implemented."
        log.save()
        return

    client = K90Client(ip_address=device.ip_address, port=device.port, password=device.connection_password)
    
    if not client.connect():
        log.status = "Failed"
        log.error_message = "Could not connect to device."
        log.end_time = now_datetime()
        log.save()
        return
        
    try:
        attendance = client.get_attendance()
        log.fetched_count = len(attendance)
        
        created = 0
        duplicates = 0
        unmapped = 0
        
        for record in attendance:
            # 1. Raw Punch Idempotency
            try:
                raw = frappe.new_doc("Biometric Raw Punch")
                raw.device = device.name
                raw.device_user_id = record["user_id"]
                raw.punch_time = record["timestamp"]
                raw.punch_type = str(record["punch_type"])
                raw.insert(ignore_permissions=True)
                frappe.db.commit()
            except frappe.DuplicateEntryError:
                duplicates += 1
                continue
                
            # 2. Map User
            employee = MappingService.get_employee_for_biometric_user(device.name, record["user_id"])
            if not employee:
                unmapped += 1
                raw.error_message = "User not mapped"
                raw.save()
                frappe.db.commit()
                continue
                
            # 3. Create Checkin
            success = CheckinService.create_employee_checkin(
                employee=employee,
                punch_time=record["timestamp"],
                device_id=device.name,
                punch_type=record["punch_type"]
            )
            
            if success:
                created += 1
                raw.processed = 1
                raw.save()
            else:
                raw.error_message = "Failed to create Employee Checkin"
                raw.save()
                
            frappe.db.commit()
            
        client.disconnect()
        
        log.created_count = created
        log.duplicate_count = duplicates
        log.unmapped_count = unmapped
        log.status = "Success"
        log.end_time = now_datetime()
        log.save()
        
        # Update device
        device.last_sync = now_datetime()
        device.last_successful_sync = now_datetime()
        device.save()
        frappe.db.commit()
        
    except Exception as e:
        client.disconnect()
        log.status = "Failed"
        log.error_message = str(e)
        log.end_time = now_datetime()
        log.save()
        frappe.db.commit()
