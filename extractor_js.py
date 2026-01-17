import re
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from datetime import date
import unicodedata

MESES_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

def parse_fecha_boletin(s: str) -> date:
    # Acepta: "09-ene.-2026", "09-ene-2026", "09-ENE.-2026"
    s = s.strip().lower().replace(".", "")
    dd, mon, yyyy = s.split("-")
    return date(int(yyyy), MESES_ES[mon], int(dd))


def obtener_html(URL):
    r = requests.get(URL, timeout=30)
    print(r.status_code, r.headers.get("Allow"))#r.raise_for_status()
    return r.text

def obtener_html_filtrado(URL,URL_BASE,fecha_ini="2025-12-01", fecha_fin="2026-01-31"):
    s = requests.Session()

    # 1) GET para obtener cookies y el token
    r = s.get(URL_BASE, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    token = soup.select_one("input[name='_token']")["value"]

    # 2) POST con token y fechas
    payload = {
        "_token": token,
        "fechainicial": fecha_ini,
        "fechafinal": fecha_fin
    }

    r2 = s.post(URL, data=payload, headers={"Referer": URL_BASE}, timeout=60)
    r2.raise_for_status()
    return r2.text

def obtener_links_boletines(html):
    soup = BeautifulSoup(html, "lxml")
    links = []

    for a in soup.find_all("a", href=True):
        title = a.get("title", "").lower()

        if "visualizar" in title and "boletín" in title:
            links.append(a["href"])

    return links

def extraer_externos(html: str, convertir_a_date: bool = False):
    soup = BeautifulSoup(html, "html.parser")

    filas = soup.select("#MyTable tbody tr")
    print("Filas encontradas en HTML:", len(filas))  # <- debe ser > 10 si viene todo

    resultados = []
    for tr in filas:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        fecha_txt = tds[1].get_text(" ", strip=True)  # ej: 15-ene.-2026
        a = tds[2].select_one("a[href*='/externo/']")
        if not a:
            continue

        url_externo = a["href"]
        if convertir_a_date:
            try:
                fecha_val = parse_fecha_boletin(fecha_txt)
            except Exception:
                # si alguna fecha viene en formato raro, la saltas o la guardas raw
                continue
            resultados.append((fecha_val, url_externo))
        else:
            resultados.append((fecha_txt, url_externo))

    return resultados


def obtener_fechas_y_links_boletines(html: str, convertir_a_date: bool = False):
    soup = BeautifulSoup(html, "lxml")
    resultados = []

    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        # Fecha en la 2da columna (índice 1)
        fecha_txt = tds[1].get_text(" ", strip=True)

        # Link "Visualizar el archivo del boletín" dentro de la 3ra columna
        a = tds[2].find("a", href=True, title=True)
        if not a:
            continue

        title = a.get("title", "").lower()
        if "visualizar" not in title or "boletín" not in title:
            continue

        url = a["href"]

        if convertir_a_date:
            try:
                fecha_val = parse_fecha_boletin(fecha_txt)
            except Exception:
                # si alguna fecha viene en formato raro, la saltas o la guardas raw
                continue
            resultados.append((fecha_val, url))
        else:
            resultados.append((fecha_txt, url))

    return resultados

def extraer_paginas_js(html):
    patron = re.compile(
        r'\{\s*'
        r'src:\s*"([^"]+)",\s*'
        r'thumb:\s*"([^"]+)",\s*'
        r'title:\s*"[^"]*",\s*'
        r'id:\s*"([^"]+)"\s*'
        r'\}',
        re.MULTILINE
    )

    resultados = []

    for match in patron.findall(html):
        src, thumb, id_ = match
        resultados.append({
            "id": id_,
            "src": src,
            "thumb": thumb
        })

    return resultados

def obtener_id_numerico(id_raw):
    return id_raw.split("&&")[0]


def obtener_token(url):
    return urlparse(url).path.split("/")[-1]

def normalizar_documento(obj):
    return {
        "token": obtener_token(obj["thumb"]),
        "id_num": obtener_id_numerico(obj["id"]),
        "total_paginas": 378  # ya lo sabes
    }

def generar_urls_paginas(doc, tam=2):
    urls = []

    for pagina in range(1, doc["total_paginas"] + 1):
        urls.append(
            f"https://edigital.poderjudicialcdmx.gob.mx/temporales/"
            f"{doc['token']}/{doc['id_num']}_{pagina}-{tam}.jpg"
        )

    return urls

def construir_url_temporal(src_url, id_raw, pagina, tam=2):
    token = obtener_token(src_url)
    id_num = obtener_id_numerico(id_raw)

    return (
        f"https://edigital.poderjudicialcdmx.gob.mx/temporales/"
        f"{token}/{id_num}_{pagina}-{tam}.jpg"
    )

def obtener_inicio_columnas(texto):
    texto = texto.upper()

    match = re.search(
        r"SALAS\s+(\d+)",
        texto
    )

    if not match:
        return None

    pagina_salas = int(match.group(1))
    return max(pagina_salas - 2, 1)

MESES_CONVERT = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}

def _normalizar_fechas(s: str) -> str:
    # quita acentos y normaliza espacios
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()

def extraer_fecha_y_numero_boletin(texto_ocr: str):
    t = _normalizar_fechas(texto_ocr)

    # 1) Extraer fecha tipo: viernes 9 de enero de 2026
    # (día de la semana opcional por si OCR lo rompe)
    patron_fecha = re.compile(
        r"\b(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)?\s*"
        r"(\d{1,2})\s*de\s*"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s*de\s*"
        r"(\d{4})\b"
    )
    m = patron_fecha.search(t)
    fecha = None
    if m:
        dia = int(m.group(1))
        mes_txt = m.group(2)
        anio = int(m.group(3))
        fecha = date(anio, MESES_CONVERT[mes_txt], dia)

    # 2) Extraer "Num 3" (Num, Núm, Num., Núm., etc.)
    patron_num = re.compile(r"\bnu[mn]\.?\s*(\d{1,4})\b")  # tolera OCR: num/nun
    n = patron_num.search(t)
    num = int(n.group(1)) if n else None

    return fecha, num

