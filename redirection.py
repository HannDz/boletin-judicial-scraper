import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from pathlib import Path

def crear_sesion():
    session = requests.Session()

    retries = Retry(
        total=8,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504, 522],
        allowed_methods=["GET"],
        raise_on_status=False,
        respect_retry_after_header=True
    )

    adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
    })

    return session


def extraer_url_redireccion(html):
    patron = r"window\.location\s*=\s*['\"]([^'\"]+)['\"]"
    match = re.search(patron, html)

    if match:
        return match.group(1)

    return None


def extraer_pdf_source(html: str) -> str | None:
    # Normaliza comillas tipográficas a comillas normales
    html = html.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")

    soup = BeautifulSoup(html, "html.parser")
    div = soup.select_one("div.PDFFlip#PDFF")
    if not div:
        return None

    return div.get("source")  # devuelve la URL o None


def obtener_visor_desde_thumb(html):
    match = re.search(
        r"window\.location\s*=\s*['\"]([^'\"]+)['\"]",
        html
    )
    return match.group(1) if match else None

def descargar_pdf(url_pdf: str, out_path: str = "boletin.pdf") -> str:
    r = requests.get(url_pdf, timeout=60)
    r.raise_for_status()
    Path(out_path).write_bytes(r.content)
    return out_path
