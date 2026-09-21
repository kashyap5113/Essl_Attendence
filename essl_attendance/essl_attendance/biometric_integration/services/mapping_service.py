import frappe

class MappingService:
    @staticmethod
    def get_employee_for_biometric_user(device_name, biometric_user_id):
        mapping = frappe.db.get_value(
            "Biometric User Mapping",
            {"biometric_device": device_name, "biometric_user_id": biometric_user_id, "active": 1},
            "employee"
        )
        return mapping
