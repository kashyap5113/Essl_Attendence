"""
Nginx Configuration Generator for eSSL Attendance iClock Protocol

This script generates the Nginx configuration snippet needed to route
/iclock/* requests from biometric devices to the Frappe API handlers.

Usage on the server:
    python -c "from essl_attendance.nginx_conf import print_nginx_conf; print_nginx_conf()"
    
Or manually add the configuration from docs/deployment.md to your Nginx site config.
"""


NGINX_CONF_TEMPLATE = """
# ═══════════════════════════════════════════════════════════════════════════════
# eSSL Attendance - iClock/ADMS Push Protocol Proxy
# Add this INSIDE your existing Nginx server {{ }} block for the ERPNext site
# Place it BEFORE the catch-all location / block
# ═══════════════════════════════════════════════════════════════════════════════

# Biometric device handshake + data upload
location /iclock/cdata {{
    rewrite ^(.*)$ /api/method/essl_attendance.iclock.cdata break;
    proxy_pass http://127.0.0.1:{gunicorn_port};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 30;
    client_max_body_size 1m;
}}

# Biometric device heartbeat / command polling
location /iclock/getrequest {{
    rewrite ^(.*)$ /api/method/essl_attendance.iclock.getrequest break;
    proxy_pass http://127.0.0.1:{gunicorn_port};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 10;
}}

# Biometric device command result feedback
location /iclock/devicecmd {{
    rewrite ^(.*)$ /api/method/essl_attendance.iclock.devicecmd break;
    proxy_pass http://127.0.0.1:{gunicorn_port};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 10;
}}

# ═══════════════════════════════════════════════════════════════════════════════
"""


def get_nginx_conf(gunicorn_port=8000):
    """Return the Nginx configuration snippet."""
    return NGINX_CONF_TEMPLATE.format(gunicorn_port=gunicorn_port)


def print_nginx_conf(gunicorn_port=8000):
    """Print the Nginx configuration to stdout."""
    print(get_nginx_conf(gunicorn_port))
    print("\n# Instructions:")
    print(f"# 1. Find your Nginx site config file (usually in /etc/nginx/conf.d/ or check with: ls ~/demo/config/)")
    print(f"# 2. Add the above location blocks INSIDE the server {{ }} block, BEFORE the 'location /' catch-all")
    print(f"# 3. Test: sudo nginx -t")
    print(f"# 4. Reload: sudo service nginx reload")
    print(f"# 5. Verify: curl -v https://your-site.com/iclock/getrequest?SN=test")
