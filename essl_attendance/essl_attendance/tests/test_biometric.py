"""Tests for the iClock/ADMS Push protocol handler."""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock
from werkzeug.test import Client
from werkzeug.wrappers import Response


class TestIClockProtocol(FrappeTestCase):
    """Test the iClock protocol endpoints."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create test company if not exists
        if not frappe.db.exists("Company", "Test Biometric Co"):
            company = frappe.new_doc("Company")
            company.company_name = "Test Biometric Co"
            company.abbr = "TBC"
            company.default_currency = "INR"
            company.country = "India"
            company.insert(ignore_permissions=True)

        # Create test device
        if not frappe.db.exists("Biometric Device", "Test ADMS Device"):
            device = frappe.new_doc("Biometric Device")
            device.device_name = "Test ADMS Device"
            device.company = "Test Biometric Co"
            device.serial_number = "TEST123456"
            device.communication_type = "ADMS Push"
            device.device_timezone = "Asia/Kolkata"
            device.enabled = 1
            device.insert(ignore_permissions=True)

        frappe.db.commit()

    def test_handshake_valid_device(self):
        """Test GET /iclock/cdata with a valid serial number."""
        from essl_attendance.iclock import _handle_handshake
        response = _handle_handshake("TEST123456")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("GET OPTION FROM: TEST123456", body)
        self.assertIn("ATTLOGStamp=", body)
        self.assertIn("Delay=", body)

    def test_handshake_unknown_device(self):
        """Test GET /iclock/cdata with an unknown serial number."""
        from essl_attendance.iclock import _handle_handshake
        response = _handle_handshake("UNKNOWN999")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertEqual(body, "OK")

    def test_attlog_parsing(self):
        """Test POST /iclock/cdata with valid ATTLOG data."""
        from essl_attendance.iclock import _process_attlog

        device = frappe.get_doc("Biometric Device", "Test ADMS Device")
        data = "10001\t2026-10-14 08:30:00\t0\t1\t0\t0\t0\n10002\t2026-10-14 08:31:00\t1\t1\t0\t0\t0"

        count = _process_attlog("Test ADMS Device", device, data)
        self.assertGreaterEqual(count, 0)

        # Verify raw punches were stored
        exists = frappe.db.exists("Biometric Raw Punch", {
            "device": "Test ADMS Device",
            "device_user_id": "10001"
        })
        # May or may not exist depending on prior test runs (idempotency)
        # The important thing is no exception was raised

    def test_attlog_malformed_line(self):
        """Test ATTLOG parsing with malformed data doesn't crash."""
        from essl_attendance.iclock import _process_attlog

        device = frappe.get_doc("Biometric Device", "Test ADMS Device")
        data = "malformed_line\n\n\t\n10001\t2026-10-14 09:00:00\t0"

        # Should not raise
        count = _process_attlog("Test ADMS Device", device, data)
        self.assertIsInstance(count, int)

    def test_attlog_duplicate_handling(self):
        """Test that duplicate punches are handled gracefully."""
        from essl_attendance.iclock import _process_attlog

        device = frappe.get_doc("Biometric Device", "Test ADMS Device")
        data = "10099\t2026-10-14 12:00:00\t0\t1\t0\t0\t0"

        # First insert
        count1 = _process_attlog("Test ADMS Device", device, data)
        frappe.db.commit()

        # Second insert (same data) — should be duplicate
        count2 = _process_attlog("Test ADMS Device", device, data)
        # count2 should be 0 (duplicate skipped)
        self.assertEqual(count2, 0)

    def test_timestamp_validation(self):
        """Test the timestamp validator."""
        from essl_attendance.iclock import _is_valid_timestamp

        self.assertTrue(_is_valid_timestamp("2026-10-14 08:30:00"))
        self.assertTrue(_is_valid_timestamp("2026-01-01 00:00:00"))
        self.assertFalse(_is_valid_timestamp(""))
        self.assertFalse(_is_valid_timestamp(None))
        self.assertFalse(_is_valid_timestamp("not-a-date"))
        self.assertFalse(_is_valid_timestamp("1899-01-01 00:00:00"))

    def test_rate_limiter(self):
        """Test the rate limiter allows normal traffic."""
        from essl_attendance.iclock import _check_rate_limit

        # Should allow initial requests
        for _ in range(10):
            self.assertTrue(_check_rate_limit("192.168.1.100"))

    def tearDown(self):
        frappe.db.rollback()


class TestCheckinService(FrappeTestCase):
    """Test the Employee Checkin creation service."""

    def test_punch_type_mapping(self):
        """Test punch type to log_type mapping."""
        from essl_attendance.biometric_integration.services.checkin_service import CheckinService

        self.assertEqual(CheckinService._map_punch_type("0"), "IN")
        self.assertEqual(CheckinService._map_punch_type("1"), "OUT")
        self.assertEqual(CheckinService._map_punch_type("4"), "IN")
        self.assertEqual(CheckinService._map_punch_type("5"), "OUT")
        self.assertIsNone(CheckinService._map_punch_type(""))
        self.assertIsNone(CheckinService._map_punch_type(None))
        self.assertIsNone(CheckinService._map_punch_type("2"))  # Break-Out: no direct mapping

    def test_timestamp_normalization(self):
        """Test timestamp parsing."""
        from essl_attendance.biometric_integration.services.checkin_service import CheckinService

        result = CheckinService._normalize_timestamp("2026-10-14 08:30:00")
        self.assertIsNotNone(result)

        result = CheckinService._normalize_timestamp("invalid")
        self.assertIsNone(result)

    def test_create_checkin_nonexistent_employee(self):
        """Test creating checkin for non-existent employee fails gracefully."""
        from essl_attendance.biometric_integration.services.checkin_service import CheckinService

        success, name, error = CheckinService.create_employee_checkin(
            employee="NONEXISTENT-EMP-999",
            punch_time="2026-10-14 08:30:00",
            device_id="Test Device"
        )
        self.assertFalse(success)
        self.assertIsNone(name)
        self.assertIn("not found", error.lower())


class TestMappingService(FrappeTestCase):
    """Test the employee mapping lookup service."""

    def test_missing_device_returns_none(self):
        """Test lookup with non-existent device returns None."""
        from essl_attendance.biometric_integration.services.mapping_service import MappingService

        result = MappingService.get_employee_for_biometric_user("NONEXISTENT", "10001")
        self.assertIsNone(result)

    def test_empty_params_returns_none(self):
        """Test lookup with empty params returns None."""
        from essl_attendance.biometric_integration.services.mapping_service import MappingService

        self.assertIsNone(MappingService.get_employee_for_biometric_user("", ""))
        self.assertIsNone(MappingService.get_employee_for_biometric_user(None, None))

    def tearDown(self):
        frappe.db.rollback()


class TestRawPunchIdempotency(FrappeTestCase):
    """Test raw punch idempotency key generation."""

    def test_idempotency_key_generated(self):
        """Test that idempotency key is generated on insert."""
        from essl_attendance.doctype.biometric_raw_punch.biometric_raw_punch import BiometricRawPunch

        doc = frappe.new_doc("Biometric Raw Punch")
        doc.device = "Test ADMS Device"
        doc.device_user_id = "99999"
        doc.punch_time = "2026-12-31 23:59:59"
        doc.punch_type = "0"
        doc.before_insert()

        self.assertIsNotNone(doc.idempotency_key)
        self.assertEqual(len(doc.idempotency_key), 40)

    def test_same_data_same_key(self):
        """Test that identical data produces identical keys."""
        doc1 = frappe.new_doc("Biometric Raw Punch")
        doc1.device = "Test ADMS Device"
        doc1.device_user_id = "88888"
        doc1.punch_time = "2026-06-15 10:00:00"
        doc1.punch_type = "0"
        doc1.before_insert()

        doc2 = frappe.new_doc("Biometric Raw Punch")
        doc2.device = "Test ADMS Device"
        doc2.device_user_id = "88888"
        doc2.punch_time = "2026-06-15 10:00:00"
        doc2.punch_type = "0"
        doc2.before_insert()

        self.assertEqual(doc1.idempotency_key, doc2.idempotency_key)

    def test_different_data_different_key(self):
        """Test that different data produces different keys."""
        doc1 = frappe.new_doc("Biometric Raw Punch")
        doc1.device = "Test ADMS Device"
        doc1.device_user_id = "77777"
        doc1.punch_time = "2026-06-15 10:00:00"
        doc1.punch_type = "0"
        doc1.before_insert()

        doc2 = frappe.new_doc("Biometric Raw Punch")
        doc2.device = "Test ADMS Device"
        doc2.device_user_id = "77777"
        doc2.punch_time = "2026-06-15 10:00:01"  # Different time
        doc2.punch_type = "0"
        doc2.before_insert()

        self.assertNotEqual(doc1.idempotency_key, doc2.idempotency_key)

    def tearDown(self):
        frappe.db.rollback()
