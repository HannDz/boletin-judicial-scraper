import re
import unicodedata
from typing import List, Dict, Optional
from pypdf import PdfReader
from pathlib import Path

RE_VS = re.compile(r"\bvs\.?\b", re.IGNORECASE)
RE_ARR = re.compile(r"\barrend(?:\.|amiento)?\b", re.IGNORECASE)

# estatus al final o dentro del caso
RE_STATUS = re.compile(r"\b(\d{1,3})\s*(acdos?|acdo|sent)\.?\b", re.IGNORECASE)

# expediente base: T. 942-2019-003
RE_EXP_FULL = re.compile(r"\bT\.\s*(\d{1,6})[-/](\d{4})[-/](\d{3})\b", re.IGNORECASE)
# colas: "y 006" o ", 006" (mismo prefijo/año del anterior)
RE_EXP_TAIL = re.compile(r"\b(?:y|,)\s*(\d{3})\b", re.IGNORECASE)

RE_T_DOT = re.compile(r"\bT\.\s*", re.IGNORECASE)

# Tipo de juicio que termina en Arrend/Arrendamiento y puede traer abreviaturas antes:
# "Controv. Arrend."  |  "Controv. Arrendamiento"
RE_TIPO_ARR = re.compile(
    r"(?P<tipo>(?:[A-Za-z]{2,20}\.\s*){0,4}Arrend(?:\.|amiento)?)",
    re.IGNORECASE
)
RE_PAGE_HDR = re.compile(r"\bPAGINA\s+(\d+)\s*/\s*(\d+)\b", re.IGNORECASE)

RE_NUM_BOLETIN = re.compile(
    r"\bBOLET[IÍ]N\s+JUDICIAL\s*(?:No\.?|N[úu]m\.?|Num\.?|N°|Nro\.?)\s*\.?\s*(\d{1,4})\b",
    re.IGNORECASE
)

RE_SALA_CIVIL = re.compile(
    r"\b(?P<sala>(?:PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|SEPTIMA|OCTAVA|NOVENA|DECIMA)\s+SALA\s+CIVIL)\b",
    re.IGNORECASE
)

RE_PAGE_HDR = re.compile(r"\bPAGINA\s+(\d+)\s*/\s*(\d+)\b", re.IGNORECASE)

def extraer_total_paginas(texto: str) -> Optional[int]:
    matches = list(RE_PAGE_HDR.finditer(texto))
    if not matches:
        return None
    return int(matches[-1].group(2))

def _sala_civil_para_pos(text: str, pos: int) -> Optional[str]:
    # 1) intenta dentro de la misma pagina (si existe PAGINA X/total)
    page_start = 0
    last_page = None
    for m in RE_PAGE_HDR.finditer(text):   # RE_PAGE_HDR = r"\bPAGINA\s+(\d+)\s*/\s*(\d+)\b"
        if m.start() <= pos:
            last_page = m
        else:
            break
    if last_page:
        page_start = last_page.start()

    seg = text[page_start:pos]
    matches = list(RE_SALA_CIVIL.finditer(seg))
    if matches:
        return _clean_chunk(matches[-1].group("sala")).upper()

    # 2) fallback: ventana hacia atrás (por si el encabezado de sala quedó en la página anterior)
    window_start = max(0, pos - 12000)
    seg2 = text[window_start:pos]
    matches2 = list(RE_SALA_CIVIL.finditer(seg2))
    return _clean_chunk(matches2[-1].group("sala")).upper() if matches2 else None

def extraer_numero_boletin(texto: str) -> Optional[int]:
    """
    Devuelve el primer número de boletín encontrado, ej:
    'BOLETÍN JUDICIAL No. 19' -> 19
    """
    m = RE_NUM_BOLETIN.search(texto)
    return int(m.group(1)) if m else None

def _extract_page_from_block(text: str) -> Optional[int]:
    m = RE_PAGE_HDR.search(text)
    return int(m.group(1)) if m else None

def _normalize_keep_newlines(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()

def _clean_chunk(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" .;:-")

def _extract_expedientes_sala(rest: str) -> List[str]:
    exps: List[str] = []
    for m in RE_EXP_FULL.finditer(rest):
        num, anio, folio = m.group(1), m.group(2), m.group(3)
        exps.append(f"T. {num}-{anio}-{folio}")

        tail_zone = rest[m.end(): m.end() + 70]
        for t in RE_EXP_TAIL.finditer(tail_zone):
            folio2 = t.group(1)
            exps.append(f"T. {num}-{anio}-{folio2}")

    seen = set()
    out = []
    for e in exps:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out

def parse_arrendamiento_salas_block_v2(
    block: str,
    fecha_pub: str,
    num_boletin: int,
    num_pag: Optional[int] = None
) -> List[Dict]:
    text = _normalize_keep_newlines(block)
    if not text or not RE_ARR.search(text):
        return []

    # ✅ obtiene página desde el texto agregado (PAGINA i/total)
    page_from_text = _extract_page_from_block(text)
    pagina_final = page_from_text if page_from_text is not None else num_pag
    
    num_boletin = extraer_numero_boletin(text)  # o texto de la primera página

    resultados: List[Dict] = []
    seen = set()

    # Precalcula posiciones de vs (para saber dónde empieza el "siguiente caso")
    vs_positions = [m.start() for m in RE_VS.finditer(text)]

    # Para cada match de Arrend..., construimos un caso alrededor
    for arr_m in RE_ARR.finditer(text):
        arr_pos = arr_m.start()

        pagina_caso = _pagina_para_pos(text, arr_pos) 
        sala_civil = _sala_civil_para_pos(text, arr_pos)

        # 1) Encuentra el ÚLTIMO vs antes de Arrend
        vs_before = None
        for v in vs_positions:
            if v < arr_pos:
                vs_before = v
            else:
                break
        if vs_before is None:
            continue

        # 2) case_start = fin del último estatus ANTES de ese vs (para incluir todas las líneas del actor)
        last_status = None
        for st in RE_STATUS.finditer(text[:vs_before]):
            last_status = st
        case_start = last_status.end() if last_status else 0

        # 3) case_end = inicio del siguiente vs después del actual (o fin del texto)
        next_vs = None
        for v in vs_positions:
            if v > vs_before:
                next_vs = v
                break
        case_end = next_vs if next_vs is not None else len(text)

        caso = text[case_start:case_end].strip()
        if not (RE_VS.search(caso) and RE_ARR.search(caso)):
            continue

        # 4) Separar actor vs resto
        mvs = RE_VS.search(caso)
        actor_raw = caso[:mvs.start()]
        resto = caso[mvs.end():]

        # 5) Ubicar el primer "T." (si no hay, no podemos extraer expediente)
        mt = RE_T_DOT.search(resto)
        if not mt:
            continue

        before_t = _clean_chunk(resto[:mt.start()])  # demanda + tipo
        from_t = resto[mt.start():]                  # desde T. en adelante

        # 6) tipo_juicio = última ocurrencia de (algo.) Arrend... dentro de before_t
        tipo_juicio: Optional[str] = None
        demandado_raw = before_t

        tipo_matches = list(RE_TIPO_ARR.finditer(before_t))
        if tipo_matches:
            tipo_m = tipo_matches[-1]
            tipo_juicio = _clean_chunk(tipo_m.group("tipo"))
            demandado_raw = _clean_chunk(before_t[:tipo_m.start()])

        actor = _clean_chunk(actor_raw)
        demandado = demandado_raw or None

        # 7) Estatus: toma el último estatus del caso
        estatus = None
        num_estatus = None
        st_all = list(RE_STATUS.finditer(caso))
        if st_all:
            st = st_all[-1]
            num_estatus = int(st.group(1))
            stw = st.group(2).lower()
            estatus = "Sent" if stw.startswith("sent") else "Acdo"


        # 8) Expedientes
        expedientes = _extract_expedientes_sala(from_t)
        if not expedientes:
            continue

        for exp in expedientes:
            reg = {
                "id_expediente": exp,
                "actor_demandante": actor or None,
                "demandado": demandado,
                "tipo_juicio": tipo_juicio,
                "estatus": estatus,
                "num_estatus": num_estatus,
                "fecha_publicacion": fecha_pub,
                "numero_boletin": num_boletin,
                "numero_pagina": pagina_caso,  # ✅ aquí va la página detectada
                "juzgado": sala_civil, 
            }
            key = (
                reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
                reg["tipo_juicio"], reg["estatus"], reg["fecha_publicacion"], reg["numero_boletin"],
                reg["numero_pagina"], reg["juzgado"],
            )
            if key not in seen:
                seen.add(key)
                resultados.append(reg)

    return resultados


def extraer_texto_pypdf_con_paginas(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    total = len(reader.pages)

    partes = []
    paginas_con_texto = 0

    for i, page in enumerate(reader.pages, start=1):
        texto_pag = (page.extract_text() or "").strip()
        if texto_pag:
            paginas_con_texto += 1

        partes.append(
            f"\n{'='*80}\nPAGINA {i+2}/{total+2}\n{'='*80}\n{texto_pag}\n"
        )

    partes.append(
        f"\n{'='*80}\nRESUMEN\n{'='*80}\n"
        f"Paginas totales: {total}\n"
        f"Paginas con texto: {paginas_con_texto}\n"
    )

    return "".join(partes)

RE_PAGE_HDR = re.compile(r"\bPAGINA\s+(\d+)\s*/\s*(\d+)\b", re.IGNORECASE)

def _pagina_para_pos(text: str, pos: int) -> Optional[int]:
    """
    Devuelve el número de página (PAGINA X/...) cuya cabecera está más cercana ANTES de 'pos'.
    """
    last = None
    for m in RE_PAGE_HDR.finditer(text):
        if m.start() <= pos:
            last = m
        else:
            break
    return int(last.group(1)) if last else None

def eliminar_pdf(pdf_path: str) -> bool:
    p = Path(pdf_path)
    if p.exists():
        p.unlink()   # borra el archivo
        return True
    return False