# Troubleshooting Guide

## 1. Device Shows "Never Connected" or "Offline"

**Cause:** Device is not reaching the server, or serial number mismatch.

**Check 1 — Nginx routing:**
```bash
curl -v "https://your-site.com/iclock/getrequest?SN=TEST"
# Expected: HTTP 200, body "OK"

# If you get 404 or HTML error page → Nginx location blocks not configured
# See docs/deployment.md Step 4
```

**Check 2 — Serial number:**
```bash
# Check what SN the device is sending (tail Nginx access log)
tail -f /var/log/nginx/access.log | grep iclock
# Look for: GET /iclock/getrequest?SN=<serial>

# Compare to what's in the Device record in ERPNext
# They must match exactly (case-sensitive)
```

**Check 3 — Device network:**
- Can the device ping the server? (from device diagnostic menu)
- Is port 443 (or 80) open? Test from another machine:
  ```bash
  telnet your-site.com 443
  ```

**Check 4 — Frappe workers:**
```bash
cd ~/demo
bench status
# All workers (web, short, long, scheduler) must be "running"

bench restart   # if any are stopped
```

---

## 2. Punches Not Creating Employee Checkin

**Step 1 — Check Raw Punch records:**
Go to **Biometric Raw Punch** list. Filter by your device.

| Processing Status | Meaning | Fix |
|---|---|---|
| `Pending` | Not yet processed | Rare — check workers |
| `Unmapped` | No employee mapping found | Create Biometric User Mapping |
| `Failed` | Error during checkin creation | Check error_message field |
| `Processed` | ✅ Done | — |

**Step 2 — Check Error Log in Frappe:**
```python
# In bench console:
bench --site your-site.com console

>>> logs = frappe.get_all("Error Log", filters={"method": ["like", "%iclock%"]}, 
...     fields=["title", "error", "creation"], order_by="creation desc", limit=10)
>>> for l in logs: print(l.title, l.creation)
```

**Step 3 — Fix unmapped users:**
1. Go to **Biometric User Mapping → New**
2. Select the device, enter the Device User ID (from the Raw Punch record)
3. Link to the Employee
4. On the **Biometric Device** form → Actions → **Reprocess Failed Punches**

---

## 3. Duplicate Punches

The system uses SHA-256 `idempotency_key` per raw punch. Duplicates are silently skipped.

If you see duplicate Employee Checkins (not raw punches):
```python
# Find duplicates in Employee Checkin
bench --site your-site.com console
>>> frappe.db.sql("""
...     SELECT employee, time, COUNT(*) as cnt 
...     FROM `tabEmployee Checkin`
...     GROUP BY employee, time
...     HAVING cnt > 1
...     LIMIT 10
... """, as_dict=True)
```

Delete duplicates manually. Then improve checkin dedup logic if needed.

---

## 4. Sync Log Always Shows "Failed"

Check `error_message` field in the Sync Log.

Common causes:
- **"Could not connect to device"** — TCP/IP device unreachable (check IP, firewall, network)
- **"Unsupported communication type"** — Device set to `ADMS Push` but trying to poll — change to correct type
- **"pyzk not installed"** — For TCP mode: `pip install pyzk`

---

## 5. Scheduler Not Running

```bash
cd ~/demo

# Check scheduler status
bench --site your-site.com scheduler status

# Enable if disabled
bench --site your-site.com enable-scheduler

# Check scheduled jobs
bench --site your-site.com console
>>> frappe.get_all("Scheduled Job Log", order_by="creation desc", limit=5,
...     fields=["scheduled_job_type", "status", "creation"])
```

---

## 6. Nginx Rewrites Not Working

After editing Nginx config:
```bash
# Test config syntax
sudo nginx -t

# If syntax OK, reload
sudo service nginx reload

# Check if location blocks are in the right server{} block
grep -n "iclock" /etc/nginx/conf.d/*.conf
```

If the bench regenerates Nginx config and overwrites your changes:
```bash
# Add the location blocks to a separate file that gets included
# Check if bench config includes custom includes
grep "include" ~/demo/config/nginx.conf
```

---

## 7. HTTPS / TLS Errors from Device

If the device can't connect over HTTPS:

**Option A — Try HTTP first:**
Configure the device with `http://` (port 80) to confirm protocol works.

**Option B — Adjust TLS settings:**
In Nginx:
```nginx
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:HIGH:!aNULL:!MD5;
ssl_prefer_server_ciphers on;
```

---

## 8. Useful Bench Commands

```bash
# View recent Frappe error logs
bench --site your-site.com console
>>> frappe.get_all("Error Log", order_by="creation desc", limit=10, fields=["title","creation"])

# Check last sync logs
>>> frappe.get_all("Biometric Sync Log", order_by="creation desc", limit=5,
...     fields=["device","status","created_count","failed_count","error_message"])

# Check device status
>>> frappe.db.get_value("Biometric Device", "Your Device Name",
...     ["connection_status","last_heartbeat","last_error"])

# Force reprocess all unmapped punches for a device
>>> from essl_attendance.biometric_integration.services.sync_service import reprocess_failed_punches
>>> reprocess_failed_punches("Your Device Name")

# View tail of Frappe logs
tail -f ~/demo/logs/worker.log
tail -f ~/demo/logs/web.log
tail -f ~/demo/logs/scheduler.log
```

---

## 9. Check What the Device Is Actually Sending

Enable Nginx request logging temporarily:

```nginx
# Add to your server block temporarily
location /iclock/ {
    access_log /var/log/nginx/iclock_debug.log;
    # ... rest of config
}
```

Then:
```bash
tail -f /var/log/nginx/iclock_debug.log
```

This shows every request from the device — URL, method, timestamp.

---

## 10. Rate Limiting

If your device is rate-limited (too many requests per minute), you'll see `429` responses in the Nginx log. Default limit is 200 requests/minute/IP.

To adjust, edit `essl_attendance/iclock.py`:
```python
RATE_LIMIT_MAX = 200   # increase if needed
RATE_LIMIT_WINDOW = 60  # seconds
```

Then restart workers: `bench restart`
