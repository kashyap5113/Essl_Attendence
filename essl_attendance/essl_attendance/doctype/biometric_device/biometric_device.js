frappe.ui.form.on('Biometric Device', {
    refresh: function(frm) {
        // Show connection status indicator
        if (frm.doc.connection_status === 'Online') {
            frm.dashboard.set_headline_alert(
                '<span class="indicator-pill green">● Online</span> Last heartbeat: ' +
                frappe.datetime.prettyDate(frm.doc.last_heartbeat)
            );
        } else if (frm.doc.connection_status === 'Offline') {
            frm.dashboard.set_headline_alert(
                '<span class="indicator-pill orange">● Offline</span>' +
                (frm.doc.last_heartbeat ? ' Last seen: ' + frappe.datetime.prettyDate(frm.doc.last_heartbeat) : '')
            );
        } else {
            frm.dashboard.set_headline_alert(
                '<span class="indicator-pill grey">● Never Connected</span>'
            );
        }

        // Test Connection button (TCP/IP only)
        if (frm.doc.communication_type === 'TCP/IP (LAN Only)' && !frm.is_new()) {
            frm.add_custom_button(__('Test Connection'), function() {
                frappe.call({
                    method: 'essl_attendance.api.test_device_connection',
                    args: { device_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Testing connection...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint({
                                title: __('Connection Successful'),
                                indicator: 'green',
                                message: __('Successfully connected to device at {0}:{1}',
                                    [frm.doc.ip_address, frm.doc.port])
                            });
                        } else {
                            frappe.msgprint({
                                title: __('Connection Failed'),
                                indicator: 'red',
                                message: r.message ? r.message.error : __('Could not connect to device')
                            });
                        }
                    }
                });
            }, __('Actions'));
        }

        // Manual Sync button (TCP/IP and Dummy only)
        if (['TCP/IP (LAN Only)', 'Dummy Data (Testing)'].includes(frm.doc.communication_type)
            && frm.doc.enabled && !frm.is_new()) {
            frm.add_custom_button(__('Sync Now'), function() {
                frappe.call({
                    method: 'essl_attendance.api.manual_sync',
                    args: { device_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Syncing attendance data...'),
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint({
                                title: __('Sync Complete'),
                                indicator: r.message.status === 'Success' ? 'green' : 'orange',
                                message: __('Created: {0}, Duplicates: {1}, Unmapped: {2}, Failed: {3}',
                                    [r.message.created || 0, r.message.duplicates || 0,
                                     r.message.unmapped || 0, r.message.failed || 0])
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Actions'));
        }

        // Reprocess Failed Punches button
        if (!frm.is_new()) {
            frm.add_custom_button(__('Reprocess Failed Punches'), function() {
                frappe.call({
                    method: 'essl_attendance.api.reprocess_failed_punches',
                    args: { device_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Reprocessing failed punches...'),
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint({
                                title: __('Reprocessing Complete'),
                                indicator: 'green',
                                message: __('Processed: {0}, Still Failed: {1}',
                                    [r.message.processed || 0, r.message.failed || 0])
                            });
                        }
                    }
                });
            }, __('Actions'));
        }
    }
});
