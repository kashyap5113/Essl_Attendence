# Deployment Guide

## Server Details
- Server IP: `72.62.241.183`
- Bench path: `~/demo`
- ERPNext site: configure per-client (e.g., `demo.itfarmer.in`)

---

## Step 1 — Pre-flight Checks

```bash
# SSH into the server
ssh skydot@72.62.241.183

# Verify bench is working
cd ~/demo
bench version

# Check existing sites
bench --site demo.itfarmer.in doctor

# Create a git backup of the app before any changes
cd ~/demo/apps/essl_attendance
git status
git stash   # if you have local changes to preserve
```

---

## Step 2 — Install / Update the App on the Bench

```bash
cd ~/demo

# If app is not yet on the bench:
bench get-app essl_attendance https://github.com/kashyap5113/Essl_Attendence.git

# If app is already on the bench and you're updating:
bench update --apps essl_attendance --no-backup
```

---

## Step 3 — Install on a Site and Run Migrations

```bash
# Install app on a specific site (run for each client site)
bench --site demo.itfarmer.in install-app essl_attendance

# Run migrations (creates/updates DocType tables, applies patches)
bench --site demo.itfarmer.in migrate
```

Expected output: DocType tables created for `Biometric Device`, `Biometric Raw Punch`, `Biometric Sync Log`, `Biometric User Mapping`.

---

## Step 4 — Nginx Configuration (ONE-TIME per server)

This maps `/iclock/*` URLs to the Frappe API handlers. Done once — works for all sites on the server.

### Find your Nginx config file

```bash
# Frappe bench generates its Nginx config here:
cat ~/demo/config/nginx.conf | head -50

# The active site config is usually included from /etc/nginx/conf.d/
ls /etc/nginx/conf.d/
# or
ls /etc/nginx/sites-enabled/
```

### Generate the iClock location blocks

```bash
# From the bench
bench --site demo.itfarmer.in execute "from essl_attendance.nginx_conf import print_nginx_conf; print_nginx_conf()"
```

### Edit the Nginx config

Open your site's Nginx server block and add the location blocks **before** the `location /` catch-all:

```nginx
server {
    listen 443 ssl;
    server_name demo.itfarmer.in;
    
    # ... existing SSL and other config ...

    # ── eSSL iClock Biometric Push ──────────────────────────────────────
    location /iclock/cdata {
        rewrite ^(.*)$ /api/method/essl_attendance.iclock.cdata break;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30;
        client_max_body_size 1m;
    }

    location /iclock/getrequest {
        rewrite ^(.*)$ /api/method/essl_attendance.iclock.getrequest break;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 10;
    }

    location /iclock/devicecmd {
        rewrite ^(.*)$ /api/method/essl_attendance.iclock.devicecmd break;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 10;
    }
    # ────────────────────────────────────────────────────────────────────

    location / {
        # ... existing Frappe proxy config ...
    }
}
```

> **Important:** If the bench manages the Nginx config (via `bench setup nginx`), add the location blocks in a separate include file to avoid them being overwritten on the next `bench setup nginx`. Create `/etc/nginx/conf.d/iclock.conf` and include it.

### Alternative: Separate include file (recommended)

```bash
# Create a standalone file that won't be overwritten by bench setup nginx
sudo nano /etc/nginx/conf.d/iclock_biometric.conf
```

Contents:
```nginx
# This file is managed manually — do not overwrite.
# iClock location blocks must be placed inside the correct server{} block.
# See /etc/nginx/conf.d/demo.itfarmer.in.conf and add them there.
```

### Test and reload Nginx

```bash
sudo nginx -t
sudo service nginx reload
# or
sudo systemctl reload nginx
```

---

## Step 5 — Verify Endpoints

```bash
# Test from the server itself
curl -s "http://127.0.0.1:8000/api/method/essl_attendance.iclock.getrequest?SN=TEST"
# Expected: {"message": "OK"} (Frappe wraps it)

# Test through Nginx
curl -v "https://demo.itfarmer.in/iclock/getrequest?SN=TEST"
# Expected: HTTP 200, body = OK (plain text)
```

---

## Step 6 — Restart Workers

```bash
cd ~/demo
bench restart
```

Verify workers are running:
```bash
bench status
# Should show: web, worker (short/long/default), scheduler — all running
```

---

## Step 7 — ERPNext Configuration (per client)

1. Log into the ERPNext site
2. Go to **Biometric Attendance** (in the sidebar or search)
3. Create a **Biometric Device** record:
   - Device Name: e.g., `Office K90 Pro`
   - Company: select the client's company
   - Serial Number: from the device's About/Info screen
   - Communication Type: `ADMS Push`
   - Device Timezone: `Asia/Kolkata` (or client's local timezone)
   - Enabled: ✅
4. Note the **Server URL** shown on the form
5. Create **Biometric User Mapping** records for each employee

---

## Step 8 — Physical Device Configuration

On the K90 Pro device:

```
Menu → Comm. → Cloud Server Settings
  Server Address: https://demo.itfarmer.in
  Server Port:    443
  Enable Domain:  ON
  Save → Reboot
```

After reboot, the device will send a handshake within 30 seconds.
Watch for `connection_status = Online` on the Device form.

---

## Step 9 — Acceptance Checks

- [ ] `curl https://demo.itfarmer.in/iclock/getrequest?SN=TEST` returns `200 OK`
- [ ] Device shows `Online` status in ERPNext within 2 minutes of reboot
- [ ] Punch on the device → Raw Punch appears in `Biometric Raw Punch` within 60 seconds
- [ ] Raw Punch status is `Processed` (not `Unmapped`) for mapped employees
- [ ] Employee Checkin record created in HRMS
- [ ] Sync Log shows `Success`

---

## Rollback Procedure

```bash
cd ~/demo

# 1. Find the previous working commit
git -C apps/essl_attendance log --oneline -10

# 2. Checkout the previous version
git -C apps/essl_attendance checkout <commit-hash>

# 3. Re-run migrate (will revert to previous schema if patches support it)
bench --site demo.itfarmer.in migrate

# 4. Restart
bench restart
```

> **Note:** DocType field additions are non-destructive. Rolling back removes new fields from the JSON but does NOT drop database columns. Data is safe.

---

## Adding a New Client Site

```bash
cd ~/demo

# Create new site (if not already created)
bench new-site newclient.com --db-name newclient_db

# Install ERPNext and HRMS (if not already)
bench --site newclient.com install-app erpnext
bench --site newclient.com install-app hrms

# Install biometric app — takes ~10 seconds
bench --site newclient.com install-app essl_attendance
bench --site newclient.com migrate

# Nginx — NO CHANGES NEEDED (already configured)
# Configure device + user mappings in ERPNext UI
```
