# import re
# import unicodedata
# from typing import List, Dict, Optional
# from pypdf import PdfReader
# # --- Regex base ---
# RE_VS = re.compile(r"\bvs\.?\b", re.IGNORECASE)

# # Arrendamiento (abreviaturas y variantes)
# RE_ARR = re.compile(r"\barrend(?:\.|amiento)?\b", re.IGNORECASE)

# # Localiza el inicio del primer caso (línea que contiene "vs.")
# RE_FIRST_CASE_LINE = re.compile(r"(?m)^[^\n]{1,220}\bvs\.?\b", re.IGNORECASE)

# # Estatus al final: "2 Acdos.", "1 Acdo.", "1 Sent."
# RE_STATUS = re.compile(r"\b(\d{1,3})\s*(acdos?|acdo|sent)\.?\b", re.IGNORECASE)

# # Expediente completo: "T. 942-2019-003"
# RE_EXP_FULL = re.compile(r"\bT\.\s*(\d{1,6})[-/](\d{4})[-/](\d{3})\b", re.IGNORECASE)

# # Cola de expediente: "y 006" o ", 006" (mismo prefijo y año que el anterior)
# RE_EXP_TAIL = re.compile(r"\b(?:y|,)\s*(\d{3})\b", re.IGNORECASE)

# # Para encontrar el primer "T." en el resto y separar tipo_juicio
# RE_T_DOT = re.compile(r"\bT\.\s*", re.IGNORECASE)


# def _normalize(s: str) -> str:
#     """Normaliza OCR: quita acentos, arregla comillas raras, espacios, saltos."""
#     if not s:
#         return ""
#     # normaliza unicode (quita acentos)
#     s = unicodedata.normalize("NFKD", s)
#     s = "".join(c for c in s if not unicodedata.combining(c))

#     # comillas tipográficas
#     s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")

#     # unifica saltos/espacios
#     s = s.replace("\r\n", "\n").replace("\r", "\n")
#     s = re.sub(r"[ \t]+", " ", s)
#     s = re.sub(r"\n{2,}", "\n", s)
#     return s.strip()


# def _strip_to_first_case(text: str) -> str:
#     """Recorta encabezados: deja el texto a partir de la primera línea que contiene 'vs.'."""
#     m = RE_FIRST_CASE_LINE.search(text)
#     return text[m.start():] if m else text


# def _clean_name(name: str) -> str:
#     """Limpia nombres: compacta espacios y quita puntuación sobrante al final."""
#     name = re.sub(r"\s+", " ", name).strip()
#     name = name.strip(" .;:-")
#     return name


# def _extract_expedientes_sala(rest: str) -> List[str]:
#     """
#     Extrae expedientes del tipo:
#     - T. 942-2019-003
#     - T. 194-2019-005 y 006  -> genera 2 expedientes
#     """
#     exps: List[str] = []
#     for m in RE_EXP_FULL.finditer(rest):
#         num = m.group(1)
#         anio = m.group(2)
#         folio = m.group(3)
#         exps.append(f"T. {num}-{anio}-{folio}")

#         # busca "colas" cercanas: "y 006" / ", 006"
#         tail_zone = rest[m.end(): m.end() + 60]  # ventana corta después del match
#         for t in RE_EXP_TAIL.finditer(tail_zone):
#             folio2 = t.group(1)
#             exps.append(f"T. {num}-{anio}-{folio2}")

#     # dedupe conservando orden
#     seen = set()
#     out = []
#     for e in exps:
#         if e not in seen:
#             seen.add(e)
#             out.append(e)
#     return out


# def parse_arrendamiento_salas_block(
#     block: str,
#     fecha_pub: str,
#     num_boletin: int,
#     num_pag: int
# ) -> List[Dict]:
#     """
#     Parseo para texto tipo SALAS:
#     - Encuentra casos por patrón "actor vs. demandado"
#     - Dentro de cada caso: si contiene Arrend., extrae:
#       actor, demandado, tipo_juicio (antes del primer T.), estatus, expedientes
#     - Devuelve 1..N registros por expedientes
#     """
#     text = _normalize(block)
#     if not text:
#         return []

#     text = _strip_to_first_case(text)

#     # Si ni siquiera aparece arrendamiento en el bloque, corta rápido
#     if not RE_ARR.search(text):
#         return []

#     # Divide por casos usando la siguiente heurística:
#     # Tomamos cada "actor vs." y cortamos hasta antes del siguiente "actor vs."
#     # Para eso, obtenemos los índices donde aparece " vs. " y usamos una búsqueda de "inicio de caso" por línea.
#     starts = []
#     for m in re.finditer(r"(?m)^[^\n]{1,220}\bvs\.?\b", text, flags=re.IGNORECASE):
#         starts.append(m.start())

#     # si no detecta inicios por línea, fallback: usa toda la cadena como un solo bloque-caso
#     if not starts:
#         starts = [0]

#     # arma segmentos
#     segments = []
#     for i, st in enumerate(starts):
#         en = starts[i + 1] if i + 1 < len(starts) else len(text)
#         segments.append(text[st:en].strip())

#     resultados: List[Dict] = []
#     seen = set()

#     for seg in segments:
#         # Debe tener vs y arrendamiento
#         if not RE_VS.search(seg) or not RE_ARR.search(seg):
#             continue

#         # 1) Split actor vs demandado+rest
#         mvs = RE_VS.search(seg)
#         if not mvs:
#             continue

#         actor_raw = seg[:mvs.start()]
#         after_vs = seg[mvs.end():].strip()

#         # Heurística: demandado termina cuando empieza el "tipo/expediente"
#         # Buscamos el primer "T." (si no hay, no nos sirve)
#         mt = RE_T_DOT.search(after_vs)
#         if not mt:
#             continue

#         before_t = after_vs[:mt.start()].strip()
#         rest_from_t = after_vs[mt.start():].strip()

#         # De "before_t" queremos separar demandado y tipo_juicio.
#         # En este formato, el tipo suele estar al final: "Controv. Arrend."
#         # Tomamos como tipo la última frase que contiene Arrend..., y lo anterior es demandado.
#         tipo_juicio: Optional[str] = None
#         demandado_raw = before_t

#         # intenta aislar tipo por última ocurrencia de "arrend"
#         m_arr = list(RE_ARR.finditer(before_t))
#         if m_arr:
#             last = m_arr[-1]
#             # toma desde unas palabras antes del arrend (para capturar "Controv. Arrend.")
#             # buscamos el último punto antes de arrend, si existe
#             left = before_t.rfind(".", 0, last.start())
#             cut = left + 1 if left != -1 else max(0, last.start() - 20)
#             tipo_candidate = before_t[cut:].strip()
#             # si el candidato es muy corto, usa desde 0
#             if len(tipo_candidate) < 8:
#                 tipo_candidate = before_t.strip()

#             # demandado es lo que queda antes
#             demandado_part = before_t[:cut].strip(" .")
#             if demandado_part:
#                 demandado_raw = demandado_part
#             tipo_juicio = tipo_candidate.strip(" .")

#         actor = _clean_name(actor_raw)
#         demandado = _clean_name(demandado_raw)

#         # 2) Estatus (si existe)
#         estatus = None
#         num_estatus = None
#         ms = RE_STATUS.search(seg)
#         if ms:
#             num_estatus = int(ms.group(1))
#             st = ms.group(2).lower()
#             estatus = "Sent" if st.startswith("sent") else "Acdo"

#         # 3) Expedientes (desde el "T." hacia adelante)
#         expedientes = _extract_expedientes_sala(rest_from_t)
#         if not expedientes:
#             continue

#         # 4) Registros por expediente
#         for exp in expedientes:
#             reg = {
#                 "id_expediente": exp,
#                 "actor_demandante": actor or None,
#                 "demandado": demandado or None,
#                 "tipo_juicio": tipo_juicio,
#                 "estatus": estatus,
#                 "num_estatus": num_estatus,          # opcional (conteo)
#                 "fecha_publicacion": fecha_pub,
#                 "numero_boletin": num_boletin,
#                 "numero_pagina": num_pag,
#             }
#             key = (
#                 reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
#                 reg["tipo_juicio"], reg["estatus"], reg["numero_boletin"], reg["fecha_publicacion"]
#             )
#             if key not in seen:
#                 seen.add(key)
#                 resultados.append(reg)

#     return resultados

import re
import unicodedata
from typing import List, Dict, Optional
from pypdf import PdfReader

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
    num_pag: int
) -> List[Dict]:
    text = _normalize_keep_newlines(block)
    if not text or not RE_ARR.search(text):
        return []

    resultados: List[Dict] = []
    seen = set()

    # Precalcula posiciones de vs (para saber dónde empieza el "siguiente caso")
    vs_positions = [m.start() for m in RE_VS.finditer(text)]

    # Para cada match de Arrend..., construimos un caso alrededor
    for arr_m in RE_ARR.finditer(text):
        arr_pos = arr_m.start()

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

        before_t = _clean_chunk(resto[:mt.start()])     # demanda + tipo
        from_t = resto[mt.start():]                    # desde T. en adelante

        # 6) tipo_juicio = última ocurrencia de (algo.) Arrend... dentro de before_t
        tipo_juicio: Optional[str] = None
        demandado_raw = before_t

        tipo_matches = list(RE_TIPO_ARR.finditer(before_t))
        if tipo_matches:
            tipo_m = tipo_matches[-1]
            tipo_juicio = _clean_chunk(tipo_m.group("tipo"))

            # demandado es lo anterior al tipo (limpiando residuos de puntuación)
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
                "numero_pagina": num_pag,
            }
            key = (
                reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
                reg["tipo_juicio"], reg["estatus"], reg["fecha_publicacion"], reg["numero_boletin"]
            )
            if key not in seen:
                seen.add(key)
                resultados.append(reg)

    return resultados


def extraer_texto_pypdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)