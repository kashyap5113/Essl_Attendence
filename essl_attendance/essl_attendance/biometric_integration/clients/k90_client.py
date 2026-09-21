from .base_client import BiometricDeviceClient
from typing import List, Dict, Any, Optional

class K90Client(BiometricDeviceClient):
    def __init__(self, ip_address: str, port: int, password: Optional[str] = None):
        super().__init__(ip_address, port, password)
        self.zk = None

    def connect(self) -> bool:
        try:
            from zk import ZK
            self.zk = ZK(self.ip_address, port=self.port, timeout=10, password=self.password)
            self.conn = self.zk.connect()
            self.is_connected = True
            return True
        except Exception as e:
            self.is_connected = False
            return False

    def disconnect(self) -> bool:
        if self.zk and self.is_connected:
            self.zk.disconnect()
            self.is_connected = False
        return True

    def test_connection(self) -> bool:
        if self.connect():
            self.disconnect()
            return True
        return False

    def get_attendance(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            self.connect()
        try:
            attendance = self.conn.get_attendance()
            records = []
            for att in attendance:
                records.append({
                    "user_id": str(att.user_id),
                    "timestamp": att.timestamp,
                    "punch_type": att.punch
                })
            return records
        except Exception as e:
            return []
