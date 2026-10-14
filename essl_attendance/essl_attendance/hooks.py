from . import __version__ as app_version

app_name = "essl_attendance"
app_title = "ESSL Attendance"
app_publisher = "Developer"
app_description = "eSSL/ZKTeco Biometric Attendance Integration for ERPNext v16 / Frappe HRMS v16"
app_email = "developer@example.com"
app_license = "mit"

required_apps = ["frappe", "erpnext", "hrms"]

# ─── Scheduler Jobs ──────────────────────────────────────────────────────────
scheduler_events = {
    "cron": {
        # Poll TCP/IP and Dummy devices every 5 minutes
        "*/5 * * * *": [
            "essl_attendance.biometric_integration.services.sync_service.sync_all_devices"
        ]
    },
    "hourly": [
        # Mark ADMS Push devices as offline if no heartbeat for 10+ minutes
        "essl_attendance.doctype.biometric_device.biometric_device.BiometricDevice.mark_stale_devices_offline"
    ]
}

# ─── Fixtures (export DocType configs for easy installation) ──────────────────
# fixtures = []

# ─── Website Route Rules ─────────────────────────────────────────────────────
# Note: The /iclock/* paths are handled via Nginx rewrite rules that map to
# the Frappe API methods in essl_attendance.iclock module.
# See docs/deployment.md for the Nginx configuration.
