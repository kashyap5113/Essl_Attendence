from . import __version__ as app_version

app_name = "essl_attendance"
app_title = "ESSL Attendance"
app_publisher = "Developer"
app_description = "eSSL K90 Pro Biometric Integration for Frappe HRMS"
app_email = "developer@example.com"
app_license = "mit"

required_apps = ["frappe", "erpnext", "hrms"]

scheduler_events = {
    "cron": {
        "*/5 * * * *": [
            "essl_attendance.biometric_integration.services.sync_service.sync_all_devices"
        ]
    }
}
