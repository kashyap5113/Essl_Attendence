import abc
from typing import List, Dict, Any, Optional


class BiometricDeviceClient(abc.ABC):
    """Abstract base class for biometric device communication clients.
    
    Subclasses implement the actual protocol for connecting to and
    retrieving data from specific biometric device types.
    """

    def __init__(self, ip_address: str, port: int, password: Optional[str] = None):
        self.ip_address = ip_address
        self.port = port
        self.password = password
        self.is_connected = False

    @abc.abstractmethod
    def connect(self) -> bool:
        """Establish connection to the device. Returns True on success."""
        pass

    @abc.abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from the device. Returns True on success."""
        pass

    @abc.abstractmethod
    def test_connection(self) -> bool:
        """Test connectivity without fetching data. Returns True if reachable."""
        pass

    @abc.abstractmethod
    def get_attendance(self) -> List[Dict[str, Any]]:
        """Retrieve attendance records from the device.
        
        Returns a list of dicts with keys:
            - user_id (str): Device user PIN/ID
            - timestamp (datetime): Punch timestamp
            - punch_type (int/str): Punch status code
        """
        pass

    @abc.abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        """Get device information (model, firmware, serial, etc.)."""
        pass
