import frappe
from .base_client import BiometricDeviceClient
from typing import List, Dict, Any, Optional


class K90Client(BiometricDeviceClient):
    """Client for eSSL/ZKTeco devices using direct TCP/IP (pyzk protocol).
    
    This requires the 'pyzk' package and direct network access to the device.
    Only works when server and device are on the same LAN.
    """

    def __init__(self, ip_address: str, port: int, password: Optional[str] = None):
        super().__init__(ip_address, port, password)
        self.zk = None
        self.conn = None

    def connect(self) -> bool:
        try:
            from zk import ZK
            # Convert password: pyzk expects an integer or None
            zk_password = 0
            if self.password:
                try:
                    zk_password = int(self.password)
                except (ValueError, TypeError):
                    zk_password = 0

            self.zk = ZK(
                self.ip_address,
                port=self.port,
                timeout=10,
                password=zk_password,
                force_udp=False
            )
            self.conn = self.zk.connect()
            self.is_connected = True
            frappe.logger("biometric").info(
                f"Connected to device at {self.ip_address}:{self.port}"
            )
            return True
        except ImportError:
            frappe.log_error(
                title="pyzk not installed",
                message="Install pyzk: pip install pyzk"
            )
            self.is_connected = False
            return False
        except Exception as e:
            frappe.logger("biometric").error(
                f"Connection failed to {self.ip_address}:{self.port}: {str(e)}"
            )
            self.is_connected = False
            return False

    def disconnect(self) -> bool:
        try:
            if self.conn:
                self.conn.disconnect()
            self.is_connected = False
            self.conn = None
            return True
        except Exception:
            self.is_connected = False
            self.conn = None
            return True

    def test_connection(self) -> bool:
        if self.connect():
            self.disconnect()
            return True
        return False

    def get_attendance(self) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.conn:
            frappe.logger("biometric").error("get_attendance called without active connection")
            return []
        try:
            attendance = self.conn.get_attendance()
            if not attendance:
                return []
            records = []
            for att in attendance:
                records.append({
                    "user_id": str(att.user_id),
                    "timestamp": att.timestamp,
                    "punch_type": att.punch if hasattr(att, 'punch') else att.status
                })
            frappe.logger("biometric").info(
                f"Fetched {len(records)} records from {self.ip_address}"
            )
            return records
        except Exception as e:
            frappe.logger("biometric").error(
                f"Error fetching attendance from {self.ip_address}: {str(e)}"
            )
            return []

    def get_device_info(self) -> Dict[str, Any]:
        if not self.is_connected or not self.conn:
            return {}
        try:
            info = {}
            try:
                info["firmware"] = self.conn.get_firmware_version()
            except Exception:
                pass
            try:
                info["serial_number"] = self.conn.get_serialnumber()
            except Exception:
                pass
            try:
                info["device_name"] = self.conn.get_device_name()
            except Exception:
                pass
            return info
        except Exception:
            return {}
