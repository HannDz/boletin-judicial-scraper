import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def crear_sesion():
    session = requests.Session()

    retries = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )

    adapter = HTTPAdapter(max_retries=retries)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    return session


def extraer_url_redireccion(html):
    patron = r"window\.location\s*=\s*['\"]([^'\"]+)['\"]"
    match = re.search(patron, html)

    if match:
        return match.group(1)

    return None

def obtener_visor_desde_thumb(html):
    match = re.search(
        r"window\.location\s*=\s*['\"]([^'\"]+)['\"]",
        html
    )
    return match.group(1) if match else None

