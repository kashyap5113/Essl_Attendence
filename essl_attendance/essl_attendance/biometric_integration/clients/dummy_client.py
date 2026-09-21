from .base_client import BiometricDeviceClient
from typing import List, Dict, Any, Optional
import datetime

class DummyClient(BiometricDeviceClient):
    """
    A fake client that simulates a biometric machine.
    Used for testing when the physical K90 Pro is unavailable.
    """
    def __init__(self, ip_address: str, port: int, password: Optional[str] = None):
        super().__init__(ip_address, port, password)

    def connect(self) -> bool:
        print(f"[DummyClient] Faking connection to {self.ip_address}:{self.port}...")
        self.is_connected = True
        return True

    def disconnect(self) -> bool:
        print("[DummyClient] Disconnecting...")
        self.is_connected = False
        return True

    def test_connection(self) -> bool:
        return True

    def get_attendance(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            self.connect()
            
        print("[DummyClient] Generating fake attendance data...")
        
        # Fake a punch that happened 5 minutes ago
        fake_time = datetime.datetime.now() - datetime.timedelta(minutes=5)
        
        records = [
            {
                "user_id": "10025", # Assuming this is the test user
                "timestamp": fake_time,
                "punch_type": 0 # IN
            },
            {
                "user_id": "10025",
                "timestamp": fake_time + datetime.timedelta(minutes=1),
                "punch_type": 1 # OUT
            }
        ]
        return records

    def get_device_info(self) -> Dict[str, Any]:
        return {"model": "Dummy K90 Pro"}

    def get_users(self) -> List[Dict[str, Any]]:
        return [{"user_id": "10025", "name": "Dummy User"}]

    def clear_attendance(self) -> bool:
        return True

    def get_device_time(self) -> str:
        return str(datetime.datetime.now())

    def set_device_time(self, time_string: str) -> bool:
        return True
