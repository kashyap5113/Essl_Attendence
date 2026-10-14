# Architecture Reference

## Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Biometric Device (K90 Pro)                 │
│                   ADMS Push Protocol (HTTP/HTTPS)               │
└───────────────────────────┬─────────────────────────────────────┘
                            │  /iclock/cdata, /iclock/getrequest
                            │  /iclock/devicecmd
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx (Reverse Proxy)                         │
│  Rewrites /iclock/* → /api/method/essl_attendance.iclock.*      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Frappe / Gunicorn                           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   iclock.py                              │   │
│  │  cdata()     — Handshake + ATTLOG upload                 │   │
│  │  getrequest() — Heartbeat                                │   │
│  │  devicecmd() — Command feedback                         │   │
│  └────────────────┬────────────────────────────────────────┘   │
│                   │                                              │
│  ┌────────────────▼────────────────────────────────────────┐   │
│  │             Biometric Raw Punch (DocType)                 │   │
│  │  Durable storage — idempotency_key unique constraint     │   │
│  │  processing_status: Pending/Processed/Failed/Unmapped    │   │
│  └────────────────┬────────────────────────────────────────┘   │
│                   │                                              │
│  ┌────────────────▼────────────────────────────────────────┐   │
│  │             MappingService                               │   │
│  │  device_user_id → Employee (via Biometric User Mapping)  │   │
│  └────────────────┬────────────────────────────────────────┘   │
│                   │                                              │
│  ┌────────────────▼────────────────────────────────────────┐   │
│  │             CheckinService                               │   │
│  │  Timezone conversion, duplicate check, log_type mapping  │   │
│  └────────────────┬────────────────────────────────────────┘   │
│                   │                                              │
└───────────────────│──────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Frappe HRMS                                   │
│  Employee Checkin → Auto Attendance → Attendance → Payroll      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow — Punch to Attendance

```
1. Employee punches on K90 Pro
        ↓
2. Device buffers the punch (stores locally)
        ↓
3. Device POSTs to /iclock/cdata?SN=...&table=ATTLOG
   Body: "101\t2026-10-14 08:30:00\t0\t1\t0\t0\t0"
        ↓
4. iclock.py validates:
   - Rate limit (200 req/min/IP)
   - Serial number → Biometric Device (must be enabled)
   - Payload size (≤ 1MB)
        ↓
5. Parse ATTLOG lines → validate timestamp format
        ↓
6. Store Biometric Raw Punch (idempotency_key = SHA-256 hash)
   - DuplicateEntryError = safe skip (device retry)
        ↓
7. MappingService: device_user_id → Employee
   - Not found → processing_status = "Unmapped" (punch saved, not lost)
        ↓
8. CheckinService:
   - Convert timestamp to server timezone
   - Check for existing Employee Checkin (exact time + employee)
   - Map punch type: 0→IN, 1→OUT
   - Insert Employee Checkin via HRMS
        ↓
9. Raw Punch: processing_status = "Processed", employee_checkin = <name>
        ↓
10. Biometric Sync Log updated with counts
        ↓
11. Server responds: "OK: N" → device advances its log pointer
        ↓
12. HRMS Auto Attendance processes Employee Checkins (scheduled)
        ↓
13. Attendance records created → Payroll
```

---

## DocType Reference

### Biometric Device
Central configuration record for each physical device.

| Field | Purpose |
|---|---|
| `device_name` | Human-readable name (also the document name) |
| `company` | ERPNext company this device belongs to |
| `serial_number` | Hardware SN — matches `SN` query param from device |
| `communication_type` | `ADMS Push` / `TCP/IP (LAN Only)` / `Dummy Data (Testing)` |
| `device_timezone` | IANA timezone of the device (e.g., `Asia/Kolkata`) |
| `push_server_url` | Auto-computed URL to configure on the device |
| `connection_status` | Online / Offline / Never Connected (updated by heartbeat) |
| `last_heartbeat` | Timestamp of last `/iclock/getrequest` call |
| `attlog_stamp` | Cursor for ADMS stamp mechanism |
| `enabled` | Master switch — disabled devices are rejected |

### Biometric Raw Punch
Immutable audit log of every punch received from devices.

| Field | Purpose |
|---|---|
| `device` | Link to Biometric Device |
| `device_user_id` | User PIN as reported by device |
| `punch_time` | Raw timestamp from device (in device timezone) |
| `punch_type` | Status code (0=IN, 1=OUT, etc.) |
| `idempotency_key` | SHA-256(device+user_id+timestamp+punch_type)[:40] |
| `processing_status` | Pending / Processed / Failed / Unmapped |
| `employee_checkin` | Link to created Employee Checkin (if successful) |
| `raw_payload` | Original ATTLOG line (for debugging) |
| `received_at` | When the server received this punch |

### Biometric User Mapping
Maps a device user ID to an ERPNext Employee.

| Field | Purpose |
|---|---|
| `biometric_device` | Link to Biometric Device |
| `biometric_user_id` | PIN registered on the device |
| `employee` | Link to Employee |
| `active` | Toggle to disable without deleting |

### Biometric Sync Log
Audit trail of each sync operation.

| Field | Purpose |
|---|---|
| `sync_type` | Push / Poll / Manual / Reprocess |
| `status` | Started / Success / Partial Success / Failed |
| `fetched_count` | Records received from device |
| `created_count` | Employee Checkins created |
| `duplicate_count` | Punches skipped (already existed) |
| `unmapped_count` | Punches with no employee mapping |
| `failed_count` | Punches that failed processing |

---

## Security Model

| Concern | Mitigation |
|---|---|
| Anonymous device requests | Serial number validation on every request |
| Spoofed serial number | Device must be pre-registered as a Biometric Device record |
| Abuse / DDoS | Rate limit: 200 req/min per IP |
| Large payload attacks | 1MB client_max_body_size in Nginx |
| Credential exposure | No credentials accepted/stored in device requests |
| Admin privilege escalation | All admin API methods require Frappe authentication |
| Log leakage | Serial numbers logged but no credentials; raw payloads truncated |
| Replay attacks | Idempotency key prevents duplicate processing |

---

## Scheduler Jobs

| Schedule | Job | Purpose |
|---|---|---|
| `*/5 * * * *` | `sync_service.sync_all_devices` | TCP/IP device polling |
| Hourly | `BiometricDevice.mark_stale_devices_offline` | Mark push devices offline after 10-min gap |

---

## Multi-Site / Multi-Client Model

The app is installed at the bench level once. Each site (client) has:
- Its own `Biometric Device` records (isolated by site database)
- Its own `Biometric User Mapping` records
- Its own Employee data
- Its own Raw Punch and Sync Log data

Nginx serves all sites from the same IP. The iClock proxy config applies server-wide — any site's device will work as long as the device sends the correct `Host` header (which it does, since you configure the server URL on the device).
