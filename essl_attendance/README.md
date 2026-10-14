# eSSL Attendance — Biometric Integration for ERPNext v16

A production-ready Frappe custom app that integrates eSSL K90 Pro (and compatible ZKTeco-firmware) biometric attendance devices with ERPNext v16 and Frappe HRMS v16.

---

## ✅ Key Features

- **Zero middleware** — the device pushes attendance data directly to your ERPNext server over HTTP/HTTPS
- **Multi-site, multi-client** — install once on the bench, configure per-site; add new clients in minutes
- **ADMS/iClock Push Protocol** — industry-standard protocol; no VPN, no port-forwarding, no client PC required
- **Optional TCP/IP polling** — for LAN-only deployments where the server can reach the device directly
- **Durable raw storage** — every punch is stored before processing; nothing is lost if mapping fails
- **Idempotent** — duplicate punches from device retries are safely ignored
- **Reprocessing** — fix a user mapping and replay all previously unmapped punches with one click
- **Automatic checkin creation** → HRMS Auto Attendance → Payroll

---

## Supported Devices

| Device | Protocol | Status |
|---|---|---|
| eSSL K90 Pro | ADMS Push (iClock) | ✅ Supported |
| eSSL K90 Pro | TCP/IP (pyzk) | ⚠️ LAN only (requires same network) |
| Other ZKTeco ADMS-compatible devices | ADMS Push | ✅ Likely compatible — hardware test required |

> **Note:** Protocol compatibility is based on documented ZKTeco ADMS specification. Actual K90 Pro hardware validation is required before production deployment.

---

## Architecture

```
K90 Pro Device
     │
     │  HTTP POST /iclock/cdata?SN=...&table=ATTLOG
     │  (device-initiated, works through NAT/firewall)
     ↓
Nginx (ERPNext server)
  /iclock/cdata    → /api/method/essl_attendance.iclock.cdata
  /iclock/getrequest → /api/method/essl_attendance.iclock.getrequest
  /iclock/devicecmd  → /api/method/essl_attendance.iclock.devicecmd
     ↓
iclock.py (ADMS handler)
  ├─ Validate serial number
  ├─ Rate limit check
  ├─ Parse ATTLOG payload
  ├─ Store Biometric Raw Punch (idempotent)
  └─ Create Employee Checkin via HRMS
     ↓
HRMS Auto Attendance → Attendance → Payroll
```

---

## Prerequisites

- ERPNext v16 with Frappe HRMS v16 installed
- A running bench (e.g., `~/demo`)
- Nginx (already configured for your ERPNext site)
- Python 3.10+
- The eSSL K90 Pro configured to use ADMS Push mode

For TCP/IP polling mode (optional, LAN-only): `pip install pyzk`

---

## Installation

### 1. Get the app

```bash
cd ~/demo
bench get-app essl_attendance https://github.com/kashyap5113/Essl_Attendence.git
```

### 2. Install on a site

```bash
bench --site your-site.com install-app essl_attendance
bench --site your-site.com migrate
```

### 3. Configure Nginx

Add the iClock routing to your site's Nginx config. Run:

```bash
python -c "from essl_attendance.nginx_conf import print_nginx_conf; print_nginx_conf()"
```

Then paste the output **inside** the `server { }` block in your Nginx config (before the `location /` block), and reload:

```bash
sudo nginx -t && sudo service nginx reload
```

### 4. Restart workers

```bash
bench restart
```

---

## New Client Setup (After Initial Installation)

When a new client needs biometric integration on the same bench:

```bash
# 1. Install app on new site (app is already on the bench)
bench --site newclient.yourdomain.com install-app essl_attendance
bench --site newclient.yourdomain.com migrate

# Nginx is already configured — no changes needed
# Just configure the device (step 3 below)
```

**Then in ERPNext (takes ~5 minutes):**

1. Go to **Biometric Attendance → Biometric Device → New**
2. Enter Device Name, Company, Serial Number
3. Copy the auto-generated **Server URL for Device**
4. On the K90 Pro: **Menu → Comm. → Cloud Server Settings → Server Address** = paste URL
5. Go to **Biometric User Mapping → New** — map each device user ID to an Employee
6. Done. Punches flow automatically within seconds.

---

## Device Setup (K90 Pro)

On the physical device:

| Setting | Value |
|---|---|
| Server Address | `https://your-site.com` (shown in Device form) |
| Server Port | `443` (HTTPS) or `80` (HTTP) |
| Enable Domain Name | ✅ ON |
| Push Protocol | ADMS / Cloud |

---

## Punch Processing Flow

```
Punch on device
    → Device batches and POSTs to /iclock/cdata?table=ATTLOG
    → iclock.py validates SN and parses ATTLOG lines
    → Each line stored as Biometric Raw Punch (idempotency_key prevents duplicates)
    → MappingService looks up Employee for device user ID
    → CheckinService creates Employee Checkin in HRMS
    → Auto Attendance processes checkin → creates Attendance
    → Payroll uses Attendance
```

If mapping is missing, punch stays as `Unmapped` status in Raw Punch — no data is lost.

---

## Security

- Device-facing endpoints (`/iclock/*`) use serial-number validation + rate limiting (200 req/min/IP)
- All admin operations (`/api/method/essl_attendance.api.*`) require authentication
- No credentials logged anywhere
- Payload size capped at 1MB per request
- Timestamps validated before storage

---

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md)

### Quick checks

```bash
# Check if iClock endpoint is reachable
curl -v "https://your-site.com/iclock/getrequest?SN=TEST"
# Expected: 200 OK with body "OK"

# Check Frappe error logs
bench --site your-site.com console
# >>> frappe.get_all("Error Log", filters={"method": ["like", "%iclock%"]}, fields=["title","error"])

# Check raw punches
# ERPNext → Biometric Attendance → Biometric Raw Punch (filter by Processing Status)

# Check sync logs
# ERPNext → Biometric Attendance → Biometric Sync Log
```

---

## Running Tests

```bash
bench --site your-site.com run-tests --app essl_attendance
```

---

## Known Limitations

1. **HTTPS on device**: Some K90 Pro firmware versions have outdated TLS cipher suites. Test with HTTP first, then upgrade to HTTPS.
2. **Punch direction**: The ADMS Status field is mapped as 0=IN, 1=OUT per protocol spec. Verify with your actual device output.
3. **pyzk TCP/IP**: Not suitable for remote devices. Only use when server and device are on the same LAN.
4. **No command queue**: Sending commands to devices (e.g., add user remotely) is not implemented in this version.

---

## Upgrade

```bash
cd ~/demo/apps/essl_attendance
git pull
cd ~/demo
bench --site your-site.com migrate
bench restart
```

---

## Rollback

```bash
cd ~/demo
git -C apps/essl_attendance checkout <previous-commit>
bench --site your-site.com migrate
bench restart
```
