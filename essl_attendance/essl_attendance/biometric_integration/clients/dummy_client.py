import frappe
from .base_client import BiometricDeviceClient
from typing import List, Dict, Any, Optional
import datetime


class DummyClient(BiometricDeviceClient):
    """Fake client for testing when a physical biometric device is unavailable.
    
    Generates predictable test data. Should ONLY be used with 
    communication_type = "Dummy Data (Testing)".
    """

    def __init__(self, ip_address: str = "127.0.0.1", port: int = 4370,
                 password: Optional[str] = None):
        super().__init__(ip_address, port, password)

    def connect(self) -> bool:
        frappe.logger("biometric").debug("DummyClient: Simulating connection")
        self.is_connected = True
        return True

    def disconnect(self) -> bool:
        frappe.logger("biometric").debug("DummyClient: Disconnecting")
        self.is_connected = False
        return True

    def test_connection(self) -> bool:
        return True

    def get_attendance(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            self.connect()

        frappe.logger("biometric").debug("DummyClient: Generating test attendance data")

        # Generate a punch that happened 5 minutes ago
        fake_time = datetime.datetime.now() - datetime.timedelta(minutes=5)

        records = [
            {
                "user_id": "10001",
                "timestamp": fake_time,
                "punch_type": 0  # IN
            },
            {
                "user_id": "10001",
                "timestamp": fake_time + datetime.timedelta(minutes=1),
                "punch_type": 1  # OUT
            }
        ]
        return records

    def get_device_info(self) -> Dict[str, Any]:
        return {
            "model": "Dummy Device (Testing)",
            "firmware": "0.0.0",
            "serial_number": "DUMMY000"
        }
