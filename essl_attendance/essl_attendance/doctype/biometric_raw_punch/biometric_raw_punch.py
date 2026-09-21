import frappe
from frappe.model.document import Document

class BiometricRawPunch(Document):
    def before_insert(self):
        if frappe.db.exists("Biometric Raw Punch", {
            "device": self.device,
            "device_user_id": self.device_user_id,
            "punch_time": self.punch_time
        }):
            frappe.throw("Duplicate Punch", exc=frappe.DuplicateEntryError)
