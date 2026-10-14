import frappe


class MappingService:
    """Service for resolving biometric device user IDs to ERPNext Employees."""

    @staticmethod
    def get_employee_for_biometric_user(device_name, biometric_user_id):
        """Look up the Employee linked to a biometric user ID on a device.
        
        Returns the Employee ID (e.g., HR-EMP-00001) or None.
        Only returns active mappings for enabled devices.
        """
        if not device_name or not biometric_user_id:
            return None

        # Check device is enabled
        device_enabled = frappe.db.get_value("Biometric Device", device_name, "enabled")
        if not device_enabled:
            return None

        employee = frappe.db.get_value(
            "Biometric User Mapping",
            {
                "biometric_device": device_name,
                "biometric_user_id": str(biometric_user_id).strip(),
                "active": 1
            },
            "employee"
        )
        return employee

    @staticmethod
    def get_unmapped_user_ids(device_name):
        """Get device user IDs from raw punches that have no mapping.
        
        Useful for the admin to see which device users need to be mapped.
        Returns a list of dicts with user_id and punch_count.
        """
        if not device_name:
            return []

        result = frappe.db.sql("""
            SELECT rp.device_user_id, COUNT(*) as punch_count
            FROM `tabBiometric Raw Punch` rp
            LEFT JOIN `tabBiometric User Mapping` um
                ON um.biometric_device = rp.device
                AND um.biometric_user_id = rp.device_user_id
                AND um.active = 1
            WHERE rp.device = %s
                AND um.name IS NULL
            GROUP BY rp.device_user_id
            ORDER BY punch_count DESC
        """, (device_name,), as_dict=True)

        return result

    @staticmethod
    def get_all_mappings(device_name):
        """Get all active mappings for a device."""
        if not device_name:
            return []

        return frappe.get_all(
            "Biometric User Mapping",
            filters={
                "biometric_device": device_name,
                "active": 1
            },
            fields=["biometric_user_id", "employee", "employee_name"]
        )
