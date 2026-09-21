import frappe
from frappe.model.document import Document

class BiometricDevice(Document):
    def validate(self):
        self.validate_ip_and_port()
        self.validate_company()
        
    def validate_ip_and_port(self):
        if self.communication_type == "TCP/IP":
            if not self.ip_address:
                frappe.throw("IP Address is mandatory for TCP/IP Communication.")
            if not self.port or self.port <= 0 or self.port > 65535:
                frappe.throw("Please enter a valid Port Number (e.g., 4370).")

    def validate_company(self):
        if not frappe.db.exists("Company", self.company):
            frappe.throw(f"Company {self.company} does not exist.")
