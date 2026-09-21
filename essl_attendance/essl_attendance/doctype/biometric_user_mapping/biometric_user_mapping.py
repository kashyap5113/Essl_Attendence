import frappe
from frappe.model.document import Document

class BiometricUserMapping(Document):
    def validate(self):
        self.validate_unique_mapping()

    def validate_unique_mapping(self):
        existing = frappe.db.exists(
            "Biometric User Mapping", 
            {
                "biometric_device": self.biometric_device, 
                "biometric_user_id": self.biometric_user_id,
                "name": ["!=", self.name]
            }
        )
        if existing:
            frappe.throw(f"Biometric User ID {self.biometric_user_id} is already mapped on this device.")
