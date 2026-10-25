"""Production entry point: gunicorn wsgi:app"""
import os
from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix

app = create_app()
# Enable only when running behind exactly one trusted hosting reverse proxy.
if os.environ.get("TRUST_PROXY_HEADERS", "0") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)
