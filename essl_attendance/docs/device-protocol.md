# ADMS / iClock Device Protocol Reference

## Protocol Overview

The eSSL K90 Pro uses the **ZKTeco ADMS (iClock) Push Protocol** — an HTTP-based protocol where the **device initiates connections to the server**. This eliminates the need for:
- VPN
- Port forwarding at the client site
- A local computer or middleware at the client office

---

## Endpoint Reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/iclock/cdata` | Handshake & registration |
| `POST` | `/iclock/cdata` | Attendance data upload |
| `GET` | `/iclock/getrequest` | Heartbeat & command polling |
| `POST` | `/iclock/devicecmd` | Command execution result |

All paths pass through Nginx and are proxied to the Frappe API method `essl_attendance.iclock.*`.

---

## 1. Handshake — `GET /iclock/cdata`

Device sends this when it boots or reconnects.

**Device Request:**
```http
GET /iclock/cdata?SN=BK1234567890&options=all&pushver=3.0.4S HTTP/1.1
Host: demo.itfarmer.in
```

Query parameters:
- `SN` — device hardware serial number
- `options` — `all` (request full config)
- `pushver` — firmware push protocol version (informational)

**Server Response (200 OK, text/plain):**
```
GET OPTION FROM: BK1234567890
ATTLOGStamp=0
OPERLOGStamp=0
ErrorDelay=30
Delay=10
TransTimes=00:00;23:59
TransInterval=1
TransFlag=1111000000
ServerVer=1.0.0
Realtime=1
```

Response fields:
- `ATTLOGStamp` — Unix timestamp or `0`; device only sends records newer than this
- `Delay` — heartbeat interval in seconds
- `TransFlag` — 12-bit flag controlling which data types are uploaded

---

## 2. Attendance Upload — `POST /iclock/cdata?table=ATTLOG`

Device sends this in real-time after each punch (or in batch after reconnection).

**Device Request:**
```http
POST /iclock/cdata?SN=BK1234567890&table=ATTLOG&Stamp=9999 HTTP/1.1
Host: demo.itfarmer.in
Content-Type: text/plain

101	2026-10-14 08:30:12	0	1	0	0	0
102	2026-10-14 08:32:00	1	1	0	0	0
```

**ATTLOG field layout (tab-separated):**

| Field | Index | Example | Description |
|---|---|---|---|
| User PIN | 0 | `101` | Device user ID / enrollment number |
| Timestamp | 1 | `2026-10-14 08:30:12` | `YYYY-MM-DD HH:MM:SS` in device local time |
| Status | 2 | `0` | Punch state (see table below) |
| Verify Mode | 3 | `1` | How identity was verified |
| Work Code | 4 | `0` | Optional job code |
| Reserved | 5-6 | `0` | Unused |

**Status codes:**

| Code | Meaning | Maps to HRMS |
|---|---|---|
| `0` | Check-In | `IN` |
| `1` | Check-Out | `OUT` |
| `2` | Break-Out | (no mapping) |
| `3` | Break-In | (no mapping) |
| `4` | OT-In | `IN` |
| `5` | OT-Out | `OUT` |

**Verify Mode codes:**

| Code | Method |
|---|---|
| `1` | Fingerprint |
| `2` | Password |
| `3` | Card |
| `15` | Face |

**Server Response (200 OK, text/plain):**
```
OK: 2
```
The number is how many records were accepted. Device uses this to advance its internal log pointer.

> **Critical:** If the server does not return `OK: N`, the device retries the same records. Our implementation stores records idempotently so retries are safe.

---

## 3. Heartbeat — `GET /iclock/getrequest`

Device polls this every `Delay` seconds (default: 10).

**Device Request:**
```http
GET /iclock/getrequest?SN=BK1234567890 HTTP/1.1
Host: demo.itfarmer.in
```

**Server Response (no commands):**
```
OK
```

**Server Response (with command — not implemented yet):**
```
C:101:DATA UPDATE USERINFO PIN=50	Name=John	Pri=0	Passwd=
```

---

## 4. Command Result — `POST /iclock/devicecmd`

Device reports back after executing a command.

**Device Request:**
```http
POST /iclock/devicecmd?SN=BK1234567890 HTTP/1.1
Content-Type: text/plain

ID=101&Return=0&CMD=DATA
```

**Server Response:**
```
OK
```

---

## Stamp Mechanism

Stamps prevent the device from re-uploading already-synced data.

1. On handshake, server returns current `ATTLOGStamp` value for the device
2. On data upload, device includes `Stamp=<value>` in query params
3. Server updates `attlog_stamp` on the Device record after processing
4. On next handshake, server returns the new stamp — device only sends newer records

---

## Retry Behavior

If the server returns anything other than `200 OK` with an `OK` body, the device:
1. Marks the records as not acknowledged
2. Retries on the next heartbeat cycle
3. May retry multiple times with exponential backoff

Our server handles retries safely because:
- Each raw punch has a unique `idempotency_key` (SHA-256 hash of device+user+timestamp+type)
- Duplicate inserts raise `DuplicateEntryError` and are silently skipped

---

## HTTPS Compatibility

> ⚠️ **Hardware testing required** before enabling HTTPS.

Some K90 Pro firmware versions support TLS 1.2 but not TLS 1.3. If HTTPS connection fails:
1. Test with HTTP first to confirm the protocol works
2. Check Nginx TLS configuration: `ssl_protocols TLSv1.2 TLSv1.3;`
3. Add `ssl_ciphers HIGH:!aNULL:!MD5;` to support older cipher suites

---

## Protocol Discovery Checklist (for unverified devices)

If you are deploying on a device not yet tested:

- [ ] Confirm device serial number format from device About screen
- [ ] Enable ADMS/Cloud Push on device and point to `http://your-server.com`
- [ ] Capture actual HTTP request with `tcpdump` or Nginx access log
- [ ] Verify ATTLOG field order matches the table above
- [ ] Confirm Status=0 is IN, Status=1 is OUT for this firmware version
- [ ] Test that returning `OK: N` prevents re-upload
- [ ] Test that failure response causes retry
- [ ] Verify HTTPS works (or document that HTTP must be used)
