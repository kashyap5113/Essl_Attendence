import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class BiometricDevice(Document):
    def validate(self):
        self.validate_serial_number()
        self.validate_communication_settings()
        self.validate_company()
        self.compute_push_server_url()

    def validate_serial_number(self):
        """Serial number is required and must be stripped of whitespace."""
        if self.serial_number:
            self.serial_number = self.serial_number.strip()

    def validate_communication_settings(self):
        """Validate IP/port are set for TCP/IP mode."""
        if self.communication_type == "TCP/IP (LAN Only)":
            if not self.ip_address:
                frappe.throw("IP Address is mandatory for TCP/IP Communication.")
            if not self.port or self.port <= 0 or self.port > 65535:
                frappe.throw("Please enter a valid Port Number (e.g., 4370).")

    def validate_company(self):
        if self.company and not frappe.db.exists("Company", self.company):
            frappe.throw(f"Company {self.company} does not exist.")

    def compute_push_server_url(self):
        """Auto-compute the URL to show admin what to configure on the device."""
        if self.communication_type == "ADMS Push":
            try:
                site_url = frappe.utils.get_url()
                self.push_server_url = site_url if site_url else ""
            except Exception:
                self.push_server_url = ""

    def update_heartbeat(self):
        """Called by iClock handler when device contacts the server."""
        frappe.db.set_value(
            "Biometric Device", self.name,
            {
                "last_heartbeat": now_datetime(),
                "connection_status": "Online",
                "last_error": ""
            },
            update_modified=False
        )

    def update_last_sync(self, success=True, error_message=None):
        """Update sync timestamps after a sync attempt."""
        values = {"last_sync": now_datetime()}
        if success:
            values["last_successful_sync"] = now_datetime()
            values["last_error"] = ""
        else:
            values["last_error"] = str(error_message or "")[:500]
        frappe.db.set_value("Biometric Device", self.name, values, update_modified=False)

    def set_error(self, error_message):
        """Record an error on the device document."""
        frappe.db.set_value(
            "Biometric Device", self.name,
            {"last_error": str(error_message or "")[:500]},
            update_modified=False
        )

    @staticmethod
    def mark_stale_devices_offline():
        """Mark ADMS Push devices as Offline if no heartbeat for 10+ minutes.
        Called by scheduler.
        """
        threshold = frappe.utils.add_to_date(now_datetime(), minutes=-10)
        stale = frappe.get_all(
            "Biometric Device",
            filters={
                "enabled": 1,
                "communication_type": "ADMS Push",
                "connection_status": "Online",
                "last_heartbeat": ["<", threshold]
            },
            pluck="name"
        )
        for name in stale:
            frappe.db.set_value(
                "Biometric Device", name,
                {"connection_status": "Offline"},
                update_modified=False
            )
        if stale:
            frappe.db.commit()
