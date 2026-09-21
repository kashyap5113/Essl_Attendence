import abc
from typing import List, Dict, Any, Optional

class BiometricDeviceClient(abc.ABC):
    def __init__(self, ip_address: str, port: int, password: Optional[str] = None):
        self.ip_address = ip_address
        self.port = port
        self.password = password
        self.is_connected = False

    @abc.abstractmethod
    def connect(self) -> bool:
        pass

    @abc.abstractmethod
    def disconnect(self) -> bool:
        pass

    @abc.abstractmethod
    def test_connection(self) -> bool:
        pass

    @abc.abstractmethod
    def get_attendance(self) -> List[Dict[str, Any]]:
        pass
