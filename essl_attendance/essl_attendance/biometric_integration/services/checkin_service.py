import frappe
from frappe.utils import now_datetime

class CheckinService:
    @staticmethod
    def create_employee_checkin(employee, punch_time, device_id, punch_type=None):
        try:
            # Check for duplicate in standard Employee Checkin just in case
            exists = frappe.db.exists("Employee Checkin", {
                "employee": employee,
                "time": punch_time
            })
            if exists:
                return False

            doc = frappe.new_doc("Employee Checkin")
            doc.employee = employee
            doc.time = punch_time
            doc.device_id = device_id
            
            # Map punch types if necessary
            if punch_type is not None:
                if str(punch_type) == "0":
                    doc.log_type = "IN"
                elif str(punch_type) == "1":
                    doc.log_type = "OUT"
                
            doc.insert(ignore_permissions=True)
            return True
        except Exception as e:
            frappe.log_error(title="Biometric Checkin Error", message=str(e))
            return False
