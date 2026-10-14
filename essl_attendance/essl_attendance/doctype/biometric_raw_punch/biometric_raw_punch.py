import hashlib
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class BiometricRawPunch(Document):
    def before_insert(self):
        self.generate_idempotency_key()
        if not self.received_at:
            self.received_at = now_datetime()

    def generate_idempotency_key(self):
        """Generate a SHA-256 based idempotency key for duplicate detection.
        Uses device + user_id + normalized timestamp + punch_type.
        The unique constraint on idempotency_key field handles race conditions.
        """
        if not self.idempotency_key:
            raw = f"{self.device}|{self.device_user_id}|{self.punch_time}|{self.punch_type or ''}"
            self.idempotency_key = hashlib.sha256(raw.encode()).hexdigest()[:40]

    def mark_processed(self, checkin_name):
        """Mark this punch as successfully processed."""
        self.processing_status = "Processed"
        self.processed = 1
        self.employee_checkin = checkin_name
        self.error_message = ""
        self.save(ignore_permissions=True)

    def mark_failed(self, error_msg):
        """Mark this punch as failed processing."""
        self.processing_status = "Failed"
        self.error_message = str(error_msg)[:500]
        self.save(ignore_permissions=True)

    def mark_unmapped(self):
        """Mark this punch as unmapped (no employee mapping found)."""
        self.processing_status = "Unmapped"
        self.error_message = "No active employee mapping found for this device user ID"
        self.save(ignore_permissions=True)

    def retry_processing(self):
        """Attempt to reprocess this punch. Called during reprocessing."""
        from essl_attendance.biometric_integration.services.mapping_service import MappingService
        from essl_attendance.biometric_integration.services.checkin_service import CheckinService

        employee = MappingService.get_employee_for_biometric_user(
            self.device, self.device_user_id
        )
        if not employee:
            self.mark_unmapped()
            return False

        success, checkin_name, error = CheckinService.create_employee_checkin(
            employee=employee,
            punch_time=self.punch_time,
            device_id=self.device,
            punch_type=self.punch_type
        )
        if success:
            self.mark_processed(checkin_name)
            return True
        else:
            self.mark_failed(error)
            return False
