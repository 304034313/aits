"""
WSGI config for aits_backend project.
"""

import os
import sys

# 与 manage.py 一致：将 apps 加入路径，否则 gunicorn/uwsgi 等入口可能无法加载 performance 等包
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APPS_DIR = os.path.join(_BACKEND_DIR, 'apps')
if _APPS_DIR not in sys.path:
    sys.path.insert(0, _APPS_DIR)

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aits_backend.settings')

application = get_wsgi_application()
