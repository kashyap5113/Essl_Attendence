import frappe
from frappe.model.document import Document


class BiometricUserMapping(Document):
    def validate(self):
        self.validate_unique_mapping()
        self.validate_employee()
        self.validate_device()

    def validate_unique_mapping(self):
        """Ensure a biometric user ID is only mapped once per device."""
        existing = frappe.db.exists(
            "Biometric User Mapping",
            {
                "biometric_device": self.biometric_device,
                "biometric_user_id": self.biometric_user_id,
                "name": ["!=", self.name]
            }
        )
        if existing:
            frappe.throw(
                f"Biometric User ID '{self.biometric_user_id}' is already mapped "
                f"on device '{self.biometric_device}'."
            )

    def validate_employee(self):
        """Check the employee exists and is active."""
        if not self.employee:
            return
        emp_status = frappe.db.get_value("Employee", self.employee, "status")
        if not emp_status:
            frappe.throw(f"Employee '{self.employee}' does not exist.")
        if emp_status != "Active" and self.active:
            frappe.msgprint(
                f"Warning: Employee '{self.employee}' status is '{emp_status}'. "
                "The mapping is being saved but the employee may not be active.",
                indicator="orange"
            )

    def validate_device(self):
        """Check the device exists."""
        if self.biometric_device and not frappe.db.exists("Biometric Device", self.biometric_device):
            frappe.throw(f"Biometric Device '{self.biometric_device}' does not exist.")
