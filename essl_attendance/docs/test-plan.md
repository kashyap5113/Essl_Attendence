# Test Plan

## Running the Test Suite

```bash
# Run all essl_attendance tests
bench --site your-test-site.com run-tests --app essl_attendance

# Run a specific test module
bench --site your-test-site.com run-tests --module essl_attendance.tests.test_biometric

# Run with verbose output
bench --site your-test-site.com run-tests --app essl_attendance --verbose
```

---

## Automated Test Coverage

### Unit Tests (no hardware required)

| Test | Class | What it verifies |
|---|---|---|
| Valid handshake | `TestIClockProtocol` | GET /iclock/cdata with known SN returns config |
| Unknown device handshake | `TestIClockProtocol` | Unknown SN returns OK (no error exposed) |
| ATTLOG parsing | `TestIClockProtocol` | Valid 7-field tab-separated data is stored |
| Malformed ATTLOG | `TestIClockProtocol` | Malformed lines don't crash the handler |
| Duplicate ATTLOG | `TestIClockProtocol` | Sending same data twice → second is skipped |
| Timestamp validation | `TestIClockProtocol` | Valid/invalid timestamp formats |
| Rate limiter | `TestIClockProtocol` | Normal traffic passes through |
| Punch type mapping | `TestCheckinService` | 0→IN, 1→OUT, 2→None, None→None |
| Timestamp normalization | `TestCheckinService` | String parsing and invalid inputs |
| Nonexistent employee | `TestCheckinService` | Returns error, does not crash |
| Missing device mapping | `TestMappingService` | Returns None safely |
| Empty params mapping | `TestMappingService` | Returns None safely |
| Idempotency key generated | `TestRawPunchIdempotency` | Key is 40-char hex string |
| Same data same key | `TestRawPunchIdempotency` | Deterministic output |
| Different data different key | `TestRawPunchIdempotency` | No collision on different timestamps |

---

## Hardware Validation Tests (requires physical K90 Pro)

These must be performed on the real device before declaring the integration production-ready.

### HW-1: Initial Connection
1. Configure device with server URL
2. Reboot device
3. **Expected:** Device form shows `Online` within 60 seconds
4. **Expected:** Sync Log entry created with type `Push`

### HW-2: Real-Time Punch
1. Punch on device (fingerprint or card)
2. Wait ≤ 60 seconds
3. **Expected:** `Biometric Raw Punch` record appears
4. **Expected:** `processing_status = Processed` (if mapping exists)
5. **Expected:** `Employee Checkin` created in HRMS

### HW-3: Unmapped User
1. Punch with a user ID that has no `Biometric User Mapping`
2. **Expected:** Raw Punch appears with `processing_status = Unmapped`
3. Create mapping, click **Reprocess Failed Punches**
4. **Expected:** Status changes to `Processed`, Employee Checkin created

### HW-4: Device Retry / Duplicate
1. Disconnect server temporarily (stop Nginx or workers)
2. Punch on device
3. Reconnect server
4. **Expected:** Device retries the punch on reconnect
5. **Expected:** Exactly ONE Raw Punch stored (no duplicate)
6. **Expected:** Exactly ONE Employee Checkin created

### HW-5: Offline Batch Upload
1. Take device offline for 30 minutes (disconnect network)
2. Make multiple punches
3. Reconnect device to network
4. **Expected:** All punches uploaded in batch
5. **Expected:** Each punch stored as separate Raw Punch record
6. **Expected:** Employee Checkins created for all (if mapped)

### HW-6: ATTLOG Field Verification
1. Check the raw ATTLOG data captured in `raw_payload` field
2. Verify field positions match the documented format:
   - Field 0: User PIN (matches device enrollment ID)
   - Field 1: Timestamp (YYYY-MM-DD HH:MM:SS in device timezone)
   - Field 2: Status (0=IN, 1=OUT)
3. If field order is different, update `_process_attlog()` in `iclock.py`

### HW-7: Stamp Verification
1. Note current `attlog_stamp` on Device record
2. Punch and confirm sync
3. Reboot device
4. **Expected:** Device sends `ATTLOGStamp=X` in handshake
5. **Expected:** Device does NOT re-upload already-synced punches

### HW-8: HTTPS Test
1. Configure device with `https://` URL
2. Reboot device
3. **Expected:** Heartbeat is received by server (device connects over TLS)
4. If fails: test with `http://` and report TLS cipher issue

### HW-9: Auto Attendance Integration
1. Ensure employee has a Shift Type assigned
2. Create IN and OUT punches on the device
3. Run Auto Attendance manually:
   ```
   HRMS → Attendance → Process Auto Attendance
   ```
4. **Expected:** Attendance record created with correct status

---

## Regression Tests After Code Changes

Before pushing any code change:
- [ ] `bench run-tests --app essl_attendance` passes
- [ ] `bench --site test.local doctor` passes
- [ ] No new entries in Frappe Error Log after test run
- [ ] Sync Log shows correct status (not false Success)
- [ ] Nginx test passes: `sudo nginx -t`

---

## Known Limitations (not tested yet)

| Item | Status | Notes |
|---|---|---|
| HTTPS on K90 Pro | ⏳ Hardware test required | TLS cipher suite compatibility unknown |
| ATTLOG field order on actual device | ⏳ Hardware test required | Documented order assumed, not confirmed |
| Stamp mechanism behavior | ⏳ Hardware test required | Need to confirm device honors stamp values |
| Multiple concurrent device punches | ⏳ Load test required | Redis lock protects TCP polling; Push mode inherently concurrent |
| Punch direction accuracy | ⏳ Hardware test required | Status 0=IN / 1=OUT assumed per spec |
