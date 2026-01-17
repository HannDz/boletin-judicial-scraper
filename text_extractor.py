import re
from typing import List, Dict, Optional

# -----------------------------
# Regex base (tolerantes a OCR)
# -----------------------------
RE_ARR = re.compile(r"\barrendamiento\b", re.IGNORECASE)

RE_VS = re.compile(r"\bvs\.?\b", re.IGNORECASE)

# tipos de juicio (puedes agregar más aquí)
RE_TIPO = re.compile(
    r"(Controv\.\s*de\s*Arrendamiento|Especial\s*de\s*Arrendamiento\s*Oral)",
    re.IGNORECASE
)

# expedientes:
# - T.Ap 1583/2024/007 (con o sin espacios/puntos)
# - T. 275/2023/001
RE_EXP = re.compile(
    r"(?:T\.?\s*Ap\.?\s*\d+/\d{4}/\d{3})|(?:T\.\s*\d+/\d{4}/\d{3})|\b\d+/\d{4}\b",
    re.IGNORECASE
)

RE_ACDO = re.compile(r"\b(?:Acdo|Acdos|Acuerdo|Acuerdos)\.?\b", re.IGNORECASE)
RE_SENT = re.compile(r"\b(?:Sent|Sentencia|Sentencias)\.?\b", re.IGNORECASE)
RE_STATUS = re.compile(r"\b(?:Acdo|Acdos|Acuerdo|Acuerdos|Sent|Sentencia|Sentencias)\.?\b", re.IGNORECASE)

# "corte" entre casos: "Acdo./Sent." seguido de un nuevo "Actor vs."
RE_CASE_BOUNDARY = re.compile(
    r"\b(?:Acdo|Sent)\.?\s+(?=[A-ZÁÉÍÓÚÑ(].{3,250}\bvs\.?\b)",
    re.IGNORECASE
)

RE_DIAS = re.compile(r"\b(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[aá]bado|Domingo)\b", re.IGNORECASE)

def _strip_headers(s: str) -> str:
    u = s.strip()

    # Encabezados típicos
    u = re.sub(r"^.*?\bACUERDOS\s+DEL\b\s+.*?\b\d{4}\b\s+", "", u, flags=re.IGNORECASE)
    u = re.sub(r"^.*?\bBOLETIN\b.*?\b\d{4}\b\s+", "", u, flags=re.IGNORECASE)
    u = re.sub(r"^.*?\b(PRIMERA|SEGUNDA|TERCERA)\s+SALA\b.*?\b\d{4}\b\s+", "", u, flags=re.IGNORECASE)

    # Basura tipo "lo. 3 Viernes 9 de enero del 2026 ..."
    if RE_DIAS.search(u) and re.search(r"\b\d{4}\b", u):
        u = re.sub(r"^.*?\b\d{4}\b\s+", "", u, flags=re.IGNORECASE)

    # Prefijos OCR comunes
    u = re.sub(r"^\s*(?:lo|l0|I0|IO|I|l)\.?\s*\d+\s*", "", u, flags=re.IGNORECASE)
    u = re.sub(r"^\s*AS\s+", "", u, flags=re.IGNORECASE)

    return u.strip()


def _normalize(text: str) -> str:
    t = text.replace("\r", " ").replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()

    # Normaliza comillas raras OCR
    t = t.replace("‘", "'").replace("’", "'").replace("´", "'").replace("“", '"').replace("”", '"')

    # Normaliza "vs"
    t = re.sub(r"\bvs\b", "vs.", t, flags=re.IGNORECASE)
    t = re.sub(r"\bvs\.\s*\.", "vs.", t, flags=re.IGNORECASE)

    # Normaliza T. Ap / T.Ap variantes
    t = re.sub(r"T\s*\.\s*Ap\s*\.", "T.Ap", t, flags=re.IGNORECASE)
    t = re.sub(r"T\s*\.?\s*Ap\b", "T.Ap", t, flags=re.IGNORECASE)
    t = re.sub(r"T\s*\.", "T.", t, flags=re.IGNORECASE)

    return t

def _clean_name_chunk(s: str) -> str:
    s = s.strip(" .,-;:|")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _extract_expedientes(block: str) -> List[str]:
    exps = [m.group(0) for m in RE_EXP.finditer(block)]

    preferidos = [e for e in exps if re.search(r"\d+/\d{4}/\d{3}$", e)]
    if preferidos:
        return [re.sub(r"\s+", " ", e).strip() for e in preferidos]

    return [re.sub(r"\s+", " ", e).strip() for e in exps]

def parse_arrendamiento_block(block: str, fecha_pub:str, num_boletin:int, num_pag:int ) -> List[Dict]:
    """
    Robusto:
    - Si el bloque trae muchos casos juntos, toma el 'vs.' más cercano ANTES del tipo Arrendamiento.
    - Extrae expedientes SOLO del segmento del caso (desde el tipo hasta antes del siguiente caso).
    - Devuelve 1..N registros si el caso trae 1..N expedientes.
    """
    block = _normalize(block)

    # Si no hay palabra clave, no es caso de arrendamiento
    if not RE_ARR.search(block):
        return []

    resultados: List[Dict] = []
    seen = set()

    # Busca todas las ocurrencias de "tipo de juicio" que incluyan Arrendamiento
    tipo_matches = list(RE_TIPO.finditer(block))

    # Si por OCR no matchea RE_TIPO pero sí "Arrendamiento", hacemos fallback
    if not tipo_matches:
        # crea un match "falso" en la primera aparición de Arrendamiento
        m_arr = RE_ARR.search(block)
        if not m_arr:
            return []
        # tipo_juicio será None en fallback
        tipo_matches = [m_arr]

    for tipo_m in tipo_matches:
        tipo_start = tipo_m.start()

        # 1) Encuentra el ÚLTIMO vs. antes del "Arrendamiento"
        vs_list = list(RE_VS.finditer(block[:tipo_start]))
        if not vs_list:
            continue
        vs_m = vs_list[-1]

        # 2) Encuentra dónde empieza este caso: después del último Acdo/Sent anterior al vs
        prev_status = None
        for m in RE_STATUS.finditer(block[:vs_m.start()]):
            prev_status = m
        case_start = prev_status.end() if prev_status else 0

        actor = _clean_name_chunk(_strip_headers(block[case_start:vs_m.start()]))

        demandado_raw = _clean_name_chunk(block[vs_m.end():tipo_start])

        # Heurística anti-ruido (ej: "su Sucesión", "vs. antes" dentro del demandado)
        lower = demandado_raw.lower()
        idx_su = lower.find(" su ")
        if idx_su != -1:
            demandado_raw = demandado_raw[:idx_su].strip()

        m_vs2 = RE_VS.search(demandado_raw)
        if m_vs2:
            demandado_raw = demandado_raw[:m_vs2.start()].strip()

        demandado = demandado_raw or None

        # 3) Define el fin del caso (antes del siguiente caso)

        # # 4) Tipo de juicio
        tipo_juicio = None
        if hasattr(tipo_m, "group") and tipo_m.re is RE_TIPO:
            tipo_juicio = tipo_m.group(1).strip()

        # 5) Estatus dentro del segmento

        # 6) Expedientes SOLO del segmento del caso

        # ✅ Corta el segmento en el PRIMER estatus después del tipo_juicio
        m_endstatus = RE_STATUS.search(block, tipo_start)
        case_end = m_endstatus.end() if m_endstatus else len(block)

        segmento = block[tipo_start:case_end]

        # ✅ Estatus directo del match
        estatus = None
        if m_endstatus:
            st = m_endstatus.group(0).lower()
            estatus = "Sent" if st.startswith("sent") else "Acdo"

        # ✅ Expedientes solo dentro del segmento (ya no se cuelan los del siguiente caso)
        expedientes = _extract_expedientes(segmento)
        for exp in expedientes:
            reg = {
                "id_expediente": exp,
                "actor_demandante": actor or None,
                "demandado": demandado,
                "tipo_juicio": tipo_juicio,
                "estatus": estatus,
                "fecha_publicacion": fecha_pub,
                "numero_boletin": num_boletin,
                "numero_pagina": num_pag,
            }
            key = (reg["id_expediente"], reg["actor_demandante"], reg["demandado"], reg["tipo_juicio"], reg["estatus"])
            if key not in seen:
                seen.add(key)
                resultados.append(reg)

    return resultados


RE_VS_LINE = re.compile(r"^\s*[A-ZÁÉÍÓÚÑ(].{3,300}\bvs\.?\b", re.IGNORECASE)
RE_CASE_LINE = re.compile(r"^\s*[A-ZÁÉÍÓÚÑ(].{3,300}\bvs\.?\b", re.IGNORECASE)
RE_END = re.compile(r"\b(Acdo|Sent)\.?\b", re.IGNORECASE)

def _is_header_line(line: str) -> bool:
    u = line.upper().strip()
    if "BOLETIN" in u or "SALA" in u or "ACUERDOS" in u:
        return True
    if len(u) <= 3:
        return True
    return False

def split_into_case_chunks(full_text: str) -> List[str]:
    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]

    chunks: List[str] = []
    current: List[str] = []
    closed = False  

    for ln in lines:
        if _is_header_line(ln):
            continue

        if RE_CASE_LINE.search(ln) and current and closed:
            chunks.append(" ".join(current).strip())
            current = []
            closed = False

        current.append(ln)

        if RE_END.search(ln):
            closed = True

    if current:
        chunks.append(" ".join(current).strip())

    return chunks

def extract_from_full_text(full_text: str) -> List[Dict]:
    results: List[Dict] = []
    seen = set()

    for chunk in split_into_case_chunks(full_text):
        if not RE_ARR.search(chunk):
            continue

        regs = parse_arrendamiento_block(chunk)
        for r in regs:
            key = (r.get("id_expediente"), r.get("actor_demandante"), r.get("demandado"), r.get("tipo_juicio"), r.get("estatus"))
            if key not in seen:
                seen.add(key)
                results.append(r)

    return results