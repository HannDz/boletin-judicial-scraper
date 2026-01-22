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
# RE_TIPO_ARR = re.compile(
#     r"(?P<tipo>(?:[A-Za-z]{2,20}\.\s*){0,4}Arrend(?:\.|amiento)?)",
#     re.IGNORECASE
# )
RE_TIPO_ARR = re.compile(
    r"(?P<tipo>(?:Controv\.?\s*)?(?:de\s+)?Arrend(?:\.|amiento)?)",
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

# RE_CASE_TERMINATOR = re.compile(
#     r"\b(?:\d{1,3}\s*(?:acdos?|acdo)\.|sent\.\s*pon\.\s*\d+\.|sent\.)\b",
#     re.IGNORECASE
# )
RE_CASE_TERMINATOR = re.compile(
    r"\b(?:\d{1,3}\s*(?:acdos?|acdo)\.?\b|sent\.?\s*pon\.?\s*\d+\.?\b|sent\.?\b)\b",
    re.IGNORECASE
)

RE_EXP_HYPH = re.compile(r"\b\d{1,6}[-/]\d{4}[-/]\d{3}\b")  # 171-2017-006, 804-2019-001
RE_TAIL_MARKERS = re.compile(r"\b(?:Cuad\.|Amp\.|Acdos?|Acdo|Sent\.?|Pon\.?)\b", re.IGNORECASE)

import re

RE_SEPARADOR = re.compile(r"=+\s*", re.IGNORECASE)
RE_PAGINA_HDR = re.compile(r"\bPAGINA\s+\d+\s*/\s*\d+\b", re.IGNORECASE)
RE_SOLO_CONSULTA = re.compile(r"(?:\bSOLO\s+CONSULTA\b[\s]*){1,}", re.IGNORECASE)

# Encabezados frecuentes (ajusta si tu OCR varía)
RE_BOLETIN_HDR = re.compile(r"\bBOLETIN\s+JUDICIAL\s+No\.?\s*\d+\b", re.IGNORECASE)
RE_FECHA_LARGA = re.compile(
    r"\b(?:Lunes|Martes|Miercoles|Mi[eé]rcoles|Jueves|Viernes|Sabado|S[áa]bado|Domingo)\s+\d{1,2}\s+de\s+[A-Za-záéíóúñ]+\s+del?\s+\d{4}\b",
    re.IGNORECASE
)

def limpiar_ruido_boletin(texto: str) -> str:
    """
    Quita marcas de agua/encabezados comunes que contaminan el parseo.
    Mantiene el contenido (nombres/casos) lo más intacto posible.
    """
    if not texto:
        return texto

    # 1) Normaliza separadores gigantes tipo ========
    texto = RE_SEPARADOR.sub(" ", texto)

    # 2) Quita PAGINA X/Y
    texto = RE_PAGINA_HDR.sub(" ", texto)

    # 3) Quita SOLO CONSULTA repetido
    texto = RE_SOLO_CONSULTA.sub(" ", texto)

    # 4) Quita encabezado BOLETIN JUDICIAL No. N (si aparece pegado al texto)
    texto = RE_BOLETIN_HDR.sub(" ", texto)

    # 5) Quita fecha larga de encabezado (si aparece pegada al texto)
    texto = RE_FECHA_LARGA.sub(" ", texto)

    # 6) Limpieza línea a línea: elimina líneas que quedaron vacías o muy “header”
    lineas = []
    for ln in texto.splitlines():
        s = ln.strip()
        if not s:
            continue
        # elimina líneas que sean solo números (ej. "50")
        if re.fullmatch(r"\d{1,4}", s):
            continue
        # elimina líneas tipo "Salas" aisladas
        if s.lower() in {"salas", "sala"}:
            continue
        lineas.append(s)

    # 7) Reconstruye
    return "\n".join(lineas)

def _case_start_before_vs(text: str, vs_start: int) -> int:
    """
    Busca el ÚLTIMO terminador de caso antes del vs.
    El inicio del caso nuevo será la línea siguiente.
    """
    window_start = max(0, vs_start - 8000)
    seg = text[window_start:vs_start]

    last = None
    for m in RE_CASE_TERMINATOR.finditer(seg):
        last = m

    if last:
        # nos vamos al fin de la línea del terminador (para saltar "No Publ..." si viene en la misma línea)
        nl = seg.find("\n", last.end())
        start = window_start + (nl + 1 if nl != -1 else last.end())
    else:
        # fallback: sube líneas para incluir actor envuelto por OCR
        start = _case_start_from_vs(text, vs_start)

    # salta espacios/saltos
    while start < len(text) and text[start] in " \n\t":
        start += 1
    return start

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

RE_STATUS_END = re.compile(r"\b(?:\d{1,3}\s*(?:acdos?|acdo)\.?\b|sent\.)", re.IGNORECASE)

def _is_header_line(line: str) -> bool:
    u = line.strip().upper()
    if not u:
        return True
    # encabezados típicos
    if u in {"SENTENCIAS", "ACUERDOS", "SALAS"}:
        return True
    if "BOLETIN JUDICIAL" in u:
        return True
    if ("SALA" in u and "CIVIL" in u and len(u) <= 40):
        return True
    if u.startswith("ACUERDOS DEL") or u.startswith("SENTENCIAS"):
        return True
    return False

RE_EXP_PARTIDO = re.compile(r"(\b\d{1,6}-\d{4})-\s*\n\s*(\d{3}\b)")

def unir_expedientes_partidos(text: str) -> str:
    # 803-2019-\n002  -> 803-2019-002
    return RE_EXP_PARTIDO.sub(r"\1-\2", text)

# def _case_start_from_vs(text: str, vs_start: int) -> int:
#     # inicio de la línea donde está el vs
#     start = text.rfind("\n", 0, vs_start) + 1

#     # sube líneas para incluir actor, hasta topar con:
#     # - otra línea con vs (caso anterior)
#     # - una línea con T. (caso anterior ya tiene expediente)
#     # - un encabezado
#     while True:
#         prev_end = start - 1
#         if prev_end <= 0:
#             break
#         prev_start = text.rfind("\n", 0, prev_end) + 1
#         prev_line = text[prev_start:prev_end].strip()

#         if _is_header_line(prev_line):
#             break
#         if RE_T_DOT.search(prev_line):      # línea ya trae expediente (caso anterior)
#             break
#         if RE_VS.search(prev_line):         # otro vs (caso anterior)
#             break

#         # si no, es parte del actor (línea envuelta por OCR)
#         start = prev_start

#     return start
# def _case_start_from_vs(text: str, vs_start: int) -> int:
#     start = text.rfind("\n", 0, vs_start) + 1

#     while True:
#         prev_end = start - 1
#         if prev_end <= 0:
#             break

#         prev_start = text.rfind("\n", 0, prev_end) + 1
#         prev_line = text[prev_start:prev_end].strip()

#         if _is_header_line(prev_line):
#             break
#         if RE_T_DOT.search(prev_line):
#             break
#         if RE_VS.search(prev_line):
#             break
#         if RE_CASE_TERMINATOR.search(prev_line):   # ✅ NUEVO
#             break

#         start = prev_start

#     return start
def _case_start_from_vs(text: str, vs_start: int) -> int:
    start = text.rfind("\n", 0, vs_start) + 1

    while True:
        prev_end = start - 1
        if prev_end <= 0:
            break

        prev_start = text.rfind("\n", 0, prev_end) + 1
        prev_line = text[prev_start:prev_end].strip()

        if _is_header_line(prev_line):
            break
        if RE_T_DOT.search(prev_line):
            break
        if RE_VS.search(prev_line):
            break

        # ✅ NUEVOS paros: cola de expediente / estatus / patrón de expediente
        if RE_CASE_TERMINATOR.search(prev_line):
            break
        if RE_EXP_HYPH.search(prev_line):
            break
        if RE_TAIL_MARKERS.search(prev_line):
            break

        start = prev_start

    return start

def _clean_actor_near_vs(actor_raw: str) -> str:
    lines = [l.strip() for l in actor_raw.split("\n") if l.strip()]
    if not lines:
        return ""

    # Tomar desde el final, acumulando líneas que NO sean cola.
    picked = []
    for line in reversed(lines):
        if RE_EXP_HYPH.search(line) or RE_TAIL_MARKERS.search(line) or RE_CASE_TERMINATOR.search(line):
            if picked:
                break
            else:
                continue
        picked.append(line)

    picked = list(reversed(picked)) if picked else [lines[-1]]
    return _clean_chunk(" ".join(picked))

def _case_end_from_vs(text: str, case_start: int, vs_start: int) -> int:
    # limita ventana para no irse al infinito
    window = text[case_start: min(len(text), case_start + 5000)]

    # busca el primer T. después del vs (dentro de la ventana)
    rel_vs = vs_start - case_start
    mt = RE_T_DOT.search(window, rel_vs)
    if not mt:
        # fallback: corta a fin de línea del vs
        nl = window.find("\n", rel_vs)
        return case_start + (nl if nl != -1 else len(window))

    # busca el primer estatus después del T. (en los siguientes ~1500 chars)
    me = RE_STATUS_END.search(window, mt.end(), min(len(window), mt.end() + 1500))
    if not me:
        # si no hay estatus, corta al fin de línea del T.
        nl = window.find("\n", mt.end())
        return case_start + (nl if nl != -1 else len(window))

    # corta al fin de la línea donde aparece el estatus
    nl = window.find("\n", me.end())
    return case_start + (nl if nl != -1 else len(window))

# def parse_arrendamiento_salas_block_v2(
#     block: str,
#     fecha_pub: str,
#     num_boletin: int,
#     num_pag: Optional[int] = None
# ) -> List[Dict]:
#     text = _normalize_keep_newlines(block)
#     if not text or not RE_ARR.search(text):
#         return []

#     # ✅ obtiene página desde el texto agregado (PAGINA i/total)
#     page_from_text = _extract_page_from_block(text)
#     pagina_final = page_from_text if page_from_text is not None else num_pag
    
#     num_boletin = extraer_numero_boletin(text)  # o texto de la primera página

#     resultados: List[Dict] = []
#     seen = set()

#     # Precalcula posiciones de vs (para saber dónde empieza el "siguiente caso")
#     vs_positions = [m.start() for m in RE_VS.finditer(text)]

#     # Para cada match de Arrend..., construimos un caso alrededor
#     for arr_m in RE_ARR.finditer(text):
#         arr_pos = arr_m.start()

#         pagina_caso = _pagina_para_pos(text, arr_pos) 
#         sala_civil = _sala_civil_para_pos(text, arr_pos)

#         # 1) Encuentra el ÚLTIMO vs antes de Arrend
#         vs_before = None
#         for v in vs_positions:
#             if v < arr_pos:
#                 vs_before = v
#             else:
#                 break
#         if vs_before is None:
#             continue

#         # 2) case_start = fin del último estatus ANTES de ese vs (para incluir todas las líneas del actor)
#         last_status = None
#         for st in RE_STATUS.finditer(text[:vs_before]):
#             last_status = st
#         case_start = last_status.end() if last_status else 0

#         # 3) case_end = inicio del siguiente vs después del actual (o fin del texto)
#         next_vs = None
#         for v in vs_positions:
#             if v > vs_before:
#                 next_vs = v
#                 break
#         case_end = next_vs if next_vs is not None else len(text)

#         caso = text[case_start:case_end].strip()
#         if not (RE_VS.search(caso) and RE_ARR.search(caso)):
#             continue

#         # 4) Separar actor vs resto
#         mvs = RE_VS.search(caso)
#         actor_raw = caso[:mvs.start()]
#         resto = caso[mvs.end():]

#         # 5) Ubicar el primer "T." (si no hay, no podemos extraer expediente)
#         mt = RE_T_DOT.search(resto)
#         if not mt:
#             continue

#         before_t = _clean_chunk(resto[:mt.start()])  # demanda + tipo
#         from_t = resto[mt.start():]                  # desde T. en adelante

#         # 6) tipo_juicio = última ocurrencia de (algo.) Arrend... dentro de before_t
#         tipo_juicio: Optional[str] = None
#         demandado_raw = before_t

#         tipo_matches = list(RE_TIPO_ARR.finditer(before_t))
#         if tipo_matches:
#             tipo_m = tipo_matches[-1]
#             tipo_juicio = _clean_chunk(tipo_m.group("tipo"))
#             demandado_raw = _clean_chunk(before_t[:tipo_m.start()])

#         actor = _clean_chunk(actor_raw)
#         demandado = demandado_raw or None

#         # 7) Estatus: toma el último estatus del caso
#         estatus = None
#         num_estatus = None
#         st_all = list(RE_STATUS.finditer(caso))
#         if st_all:
#             st = st_all[-1]
#             num_estatus = int(st.group(1))
#             stw = st.group(2).lower()
#             estatus = "Sent" if stw.startswith("sent") else "Acdo"


#         # 8) Expedientes
#         expedientes = _extract_expedientes_sala(from_t)
#         if not expedientes:
#             continue

#         for exp in expedientes:
#             reg = {
#                 "id_expediente": exp,
#                 "actor_demandante": actor or None,
#                 "demandado": demandado,
#                 "tipo_juicio": tipo_juicio,
#                 "estatus": estatus,
#                 "num_estatus": num_estatus,
#                 "fecha_publicacion": fecha_pub,
#                 "numero_boletin": num_boletin,
#                 "numero_pagina": pagina_caso,  # ✅ aquí va la página detectada
#                 "juzgado": sala_civil, 
#             }
#             key = (
#                 reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
#                 reg["tipo_juicio"], reg["estatus"], reg["fecha_publicacion"], reg["numero_boletin"],
#                 reg["numero_pagina"], reg["juzgado"],
#             )
#             if key not in seen:
#                 seen.add(key)
#                 resultados.append(reg)

#     return resultados

# def parse_arrendamiento_salas_block_v2(
#     block: str,
#     fecha_pub: str,
#     num_boletin: int,
#     num_pag: Optional[int] = None
# ) -> List[Dict]:
#     text = _normalize_keep_newlines(block)
#     if not text or not RE_ARR.search(text):
#         return []

#     # página del bloque (si tu bloque es de una sola página)
#     page_from_text = _extract_page_from_block(text)
#     pagina_final = page_from_text if page_from_text is not None else num_pag

#     # ✅ NO sobre-escribas num_boletin si en este bloque no viene el header
#     b = extraer_numero_boletin(text)
#     if b is not None:
#         num_boletin = b

#     resultados: List[Dict] = []
#     seen = set()

#     # Para cada ocurrencia de Arrend...
#     for arr_m in RE_ARR.finditer(text):
#         arr_pos = arr_m.start()

#         pagina_caso = _pagina_para_pos(text, arr_pos)
#         sala_civil = _sala_civil_para_pos(text, arr_pos)

#         # vs más cercano antes del Arrend
#         vs_list = list(RE_VS.finditer(text, 0, arr_pos))
#         if not vs_list:
#             continue
#         vs_m = vs_list[-1]

#         # ✅ NUEVOS límites del caso
#         #case_start = _case_start_from_vs(text, vs_m.start())
#         case_start = _case_start_before_vs(text, vs_m.start())

#         case_end = _case_end_from_vs(text, case_start, vs_m.start())

#         caso = text[case_start:case_end].strip()
#         if not (RE_VS.search(caso) and RE_ARR.search(caso)):
#             continue

#         # Separar actor vs resto
#         mvs = RE_VS.search(caso)
#         actor_raw = caso[:mvs.start()]
#         resto = caso[mvs.end():]

#         # Ubicar primer T.
#         mt = RE_T_DOT.search(resto)
#         if not mt:
#             continue

#         before_t = _clean_chunk(resto[:mt.start()])  # demandado + tipo
#         from_t = resto[mt.start():]

#         # Tipo/demandado (Controv. Arrend.)
#         tipo_juicio: Optional[str] = None
#         demandado_raw = before_t

#         tipo_matches = list(RE_TIPO_ARR.finditer(before_t))
#         if tipo_matches:
#             tipo_m = tipo_matches[-1]
#             tipo_juicio = _clean_chunk(tipo_m.group("tipo"))
#             demandado_raw = _clean_chunk(before_t[:tipo_m.start()])

#         #actor = _clean_chunk(actor_raw)
#         actor = _clean_actor_near_vs(actor_raw)
#         demandado = demandado_raw or None

#         # ✅ Estatus robusto (Sent. o N Acdos.)
#         estatus = None
#         num_estatus = None
#         # si hay "Sent." en el caso, es Sent
#         if re.search(r"\bSent\.\b", caso, flags=re.IGNORECASE):
#             estatus = "Sent"
#         else:
#             m_acdo = re.search(r"\b(\d{1,3})\s*(acdos?|acdo)\.?\b", caso, flags=re.IGNORECASE)
#             if m_acdo:
#                 num_estatus = int(m_acdo.group(1))
#                 estatus = "Acdo"

#         expedientes = _extract_expedientes_sala(from_t)
#         if not expedientes:
#             continue

#         for exp in expedientes:
#             reg = {
#                 "id_expediente": exp,
#                 "actor_demandante": actor or None,
#                 "demandado": demandado,
#                 "tipo_juicio": tipo_juicio,
#                 "estatus": estatus,
#                 "num_estatus": num_estatus,
#                 "fecha_publicacion": fecha_pub,
#                 "numero_boletin": num_boletin,
#                 "numero_pagina": pagina_caso if pagina_caso is not None else pagina_final,
#                 "juzgado": sala_civil,
#             }

#             key = (
#                 reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
#                 reg["tipo_juicio"], reg["estatus"], reg["fecha_publicacion"], reg["numero_boletin"],
#                 reg["numero_pagina"], reg["juzgado"],
#             )
#             if key not in seen:
#                 seen.add(key)
#                 resultados.append(reg)

#     return resultados

# def parse_arrendamiento_salas_block_v2(
#     block: str,
#     fecha_pub: str,
#     num_boletin: int,
#     num_pag: Optional[int] = None
# ) -> List[Dict]:
#     text = _normalize_keep_newlines(block)
#     if not text or not RE_ARR.search(text):
#         return []

#     # página del bloque (si tu bloque es de una sola página)
#     page_from_text = _extract_page_from_block(text)
#     pagina_final = page_from_text if page_from_text is not None else num_pag

#     # ✅ NO sobre-escribas num_boletin si en este bloque no viene el header
#     b = extraer_numero_boletin(text)
#     if b is not None:
#         num_boletin = b

#     resultados: List[Dict] = []
#     seen = set()

#     # Para cada ocurrencia de Arrend...
#     for arr_m in RE_ARR.finditer(text):
#         arr_pos = arr_m.start()

#         pagina_caso = _pagina_para_pos(text, arr_pos)
#         sala_civil = _sala_civil_para_pos(text, arr_pos)

#         # vs más cercano antes del Arrend
#         vs_list = list(RE_VS.finditer(text, 0, arr_pos))
#         if not vs_list:
#             continue
#         vs_m = vs_list[-1]

#         # ✅ NUEVOS límites del caso
#         #case_start = _case_start_from_vs(text, vs_m.start())
#         case_start = _case_start_before_vs(text, vs_m.start())

#         case_end = _case_end_from_vs(text, case_start, vs_m.start())

#         caso = text[case_start:case_end].strip()
#         if not (RE_VS.search(caso) and RE_ARR.search(caso)):
#             continue

#         # Separar actor vs resto
#         mvs = RE_VS.search(caso)
#         actor_raw = caso[:mvs.start()]
#         resto = caso[mvs.end():]

#         # Ubicar primer T.
#         mt = RE_T_DOT.search(resto)
#         if not mt:
#             continue

#         before_t = _clean_chunk(resto[:mt.start()])  # demandado + tipo
#         from_t = resto[mt.start():]

#         # Tipo/demandado (Controv. Arrend.)
#         tipo_juicio: Optional[str] = None
#         demandado_raw = before_t

#         tipo_matches = list(RE_TIPO_ARR.finditer(before_t))
#         if tipo_matches:
#             tipo_m = tipo_matches[-1]
#             tipo_juicio = _clean_chunk(tipo_m.group("tipo"))
#             demandado_raw = _clean_chunk(before_t[:tipo_m.start()])

#         #actor = _clean_chunk(actor_raw)
#         actor = _clean_actor_near_vs(actor_raw)
#         demandado = demandado_raw or None

#         # ✅ Estatus robusto (Sent. o N Acdos.)
#         estatus = None
#         num_estatus = None
#         # si hay "Sent." en el caso, es Sent
#         if re.search(r"\bSent\.\b", caso, flags=re.IGNORECASE):
#             estatus = "Sent"
#         else:
#             m_acdo = re.search(r"\b(\d{1,3})\s*(acdos?|acdo)\.?\b", caso, flags=re.IGNORECASE)
#             if m_acdo:
#                 num_estatus = int(m_acdo.group(1))
#                 estatus = "Acdo"

#         expedientes = _extract_expedientes_sala(from_t)
#         if not expedientes:
#             continue

#         for exp in expedientes:
#             reg = {
#                 "id_expediente": exp,
#                 "actor_demandante": actor or None,
#                 "demandado": demandado,
#                 "tipo_juicio": tipo_juicio,
#                 "estatus": estatus,
#                 "num_estatus": num_estatus,
#                 "fecha_publicacion": fecha_pub,
#                 "numero_boletin": num_boletin,
#                 "numero_pagina": pagina_caso if pagina_caso is not None else pagina_final,
#                 "juzgado": sala_civil,
#             }

#             key = (
#                 reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
#                 reg["tipo_juicio"], reg["estatus"], reg["fecha_publicacion"], reg["numero_boletin"],
#                 reg["numero_pagina"], reg["juzgado"],
#             )
#             if key not in seen:
#                 seen.add(key)
#                 resultados.append(reg)

#     return resultados

def parse_arrendamiento_salas_block_v2(
    block: str,
    fecha_pub: str,
    num_boletin: int,
    num_pag: Optional[int] = None
) -> List[Dict]:
    text = _normalize_keep_newlines(block)
    text = unir_expedientes_partidos(text)
    if not text:
        return []

    # Si no existe ninguna referencia a Arrend en el bloque, salimos
    if not RE_ARR.search(text):
        return []

    # Página del bloque (si el bloque trae el header PAGINA X/Y)
    page_from_text = _extract_page_from_block(text)
    pagina_final = page_from_text if page_from_text is not None else num_pag

    # No sobre-escribir num_boletin si aquí no viene el header
    b = extraer_numero_boletin(text)
    if b is not None:
        num_boletin = b

    resultados: List[Dict] = []
    seen = set()

    # Para cada ocurrencia de Arrend...
    for arr_m in RE_ARR.finditer(text):
        arr_pos = arr_m.start()

        pagina_caso = _pagina_para_pos(text, arr_pos)
        sala_civil = _sala_civil_para_pos(text, arr_pos)

        # vs más cercano antes del Arrend
        vs_list = list(RE_VS.finditer(text, 0, arr_pos))
        if not vs_list:
            continue
        vs_m = vs_list[-1]  # ESTE es el vs "correcto" para esta ocurrencia de Arrend

        # Límites del caso (tus helpers)
        case_start = _case_start_before_vs(text, vs_m.start())
        case_end = _case_end_from_vs(text, case_start, vs_m.start())

        # Segmento "caso"
        caso = text[case_start:case_end].strip()
        if not caso:
            continue

        # Debe contener Arrend (aunque sea por ruido, doble check)
        if not RE_ARR.search(caso):
            continue

        # ✅ Partir actor/resto usando el vs_m real (NO usando RE_VS.search(caso))
        vs_rel_start = vs_m.start() - case_start
        vs_rel_end = vs_m.end() - case_start

        # Seguridad por si los offsets no caen dentro del segmento
        if vs_rel_start < 0 or vs_rel_end > len(caso):
            continue

        actor_raw = caso[:vs_rel_start]
        resto = caso[vs_rel_end:]

        # Ubicar primer T.
        mt = RE_T_DOT.search(resto)
        if not mt:
            continue

        # ✅ VALIDACIÓN CLAVE:
        # Arrend debe ocurrir ENTRE el vs (vs_rel_end) y el primer T. de este caso.
        arr_rel = arr_pos - case_start                      # posición de Arrend dentro de `caso`
        t_rel = vs_rel_end + mt.start()                     # posición de T. dentro de `caso`
        if not (vs_rel_end < arr_rel < t_rel):
            # Si no se cumple, significa que este vs/T son de otro caso (ej. Ejec. Merc.)
            continue

        before_t = _clean_chunk(resto[:mt.start()])         # demandado + tipo
        from_t = resto[mt.start():]                         # desde T. en adelante

        # ✅ Otra validación: Arrend debe estar ANTES del T. en el tramo previo
        if not RE_ARR.search(before_t):
            continue

        # Tipo/demandado (Controv. Arrend.)
        tipo_juicio: Optional[str] = None
        demandado_raw = before_t

        tipo_m = None
        tipo_matches = list(RE_TIPO_ARR.finditer(before_t))
        if tipo_matches:
            tipo_m = tipo_matches[-1]

        if tipo_m:
            # Si tu RE_TIPO_ARR trae grupo (?P<tipo>...), úsalo; si no, usa group(0)
            try:
                tipo_juicio = _clean_chunk(tipo_m.group("tipo"))
            except Exception:
                tipo_juicio = _clean_chunk(tipo_m.group(0))

            demandado_raw = _clean_chunk(before_t[:tipo_m.start()])
        else:
            # Fallback: si hay Arrend pero OCR dañó el match del tipo
            tipo_juicio = "Arrend"
            m_arr = RE_ARR.search(before_t)
            if m_arr:
                demandado_raw = _clean_chunk(before_t[:m_arr.start()])

        actor = _clean_actor_near_vs(actor_raw)
        demandado = demandado_raw or None

        # Estatus: Sent. o N Acdos.
        estatus = None
        num_estatus = None

        if re.search(r"\bSent\.\b", caso, flags=re.IGNORECASE):
            estatus = "Sent"
        else:
            m_acdo = re.search(r"\b(\d{1,3})\s*(acdos?|acdo)\.?\b", caso, flags=re.IGNORECASE)
            if m_acdo:
                num_estatus = int(m_acdo.group(1))
                estatus = "Acdo"

        # Expedientes (solo de este caso, desde T. en adelante)
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
                "numero_pagina": pagina_caso if pagina_caso is not None else pagina_final,
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