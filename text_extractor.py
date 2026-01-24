import re
from typing import List, Dict, Optional
from dataclasses import dataclass

RE_TIPO = re.compile(
    r"(Controv\.\s*de\s*Arrendamiento|Especial\s*de\s*Arrendamiento\s*Oral)",
    re.IGNORECASE
)

RE_EXP = re.compile(
    r"(?:T\.?\s*Ap\.?\s*\d+/\d{4}/\d{3})|(?:T\.\s*\d+/\d{4}/\d{3})|\b\d+/\d{4}\b",
    re.IGNORECASE
)

RE_STATUS = re.compile(r"\b(?:Acdo|Acdos|Acuerdo|Acuerdos|Sent|Sentencia|Sentencias)\.?\b", re.IGNORECASE)

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

RE_ARR_ITEM = re.compile(
    r"(?P<tipo>(?:Especial|Controv)\.?\s*(?:de\s+)?Arrendamiento(?:\s+Oral)?)"
    r"\s*"
    r"T\.?\s*(?P<pref>[A-Za-z]{1,3})?\s*"
    r"(?P<num>\d{1,6})\s*[/\-]\s*(?P<anio>\d{4})\s*[/\-]\s*(?P<seq>\d{3})",
    re.IGNORECASE
)

RE_ORDINAL = re.compile(r"\b(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA)\b", re.IGNORECASE)
RE_SOLO_SALA_CIVIL = re.compile(r"^\s*SALA\s+CIV(?:IL|ÍVIL|IL)\s*$", re.IGNORECASE)

def _enriquecer_sala(m: re.Match, text: str) -> str:
    raw = _clean_chunk(m.group(0))

    # Si ya trae ordinal, úsala tal cual (limpia)
    if RE_ORDINAL.search(raw):
        return raw

    # Si es solo "SALA CIVIL", intenta recuperar el ordinal mirando hacia atrás
    if RE_SOLO_SALA_CIVIL.match(raw):
        ctx = text[max(0, m.start() - 200): m.start()]  # ventana previa
        ords = list(RE_ORDINAL.finditer(ctx))
        if ords:
            ordw = ords[-1].group(1).upper()
            return f"{ordw} SALA CIVIL"

    return raw

def _clean_name_chunk(s: str) -> str:
    s = s.strip(" .,-;:|")
    s = re.sub(r"\s+", " ", s).strip()
    return s

RE_EXP_PARTIDO = re.compile(r"(\b\d{1,6}[/\-]\d{4}[/\-])\s*\n\s*(\d{3}\b)")

def unir_expedientes_partidos(text: str) -> str:
    return RE_EXP_PARTIDO.sub(r"\1\2", text)

# Item de arrendamiento: (tipo arrend) + T. + serie(opcional) + num/anio/cons
RE_ITEM_ARREND = re.compile(
    r"(?P<tipo>"
    r"(?:\w{2,15}[-])?\s*"                 # prefijo opcional: Cnpeyf-
    r"(?:Controv\.?|Especial)\s*"          # Controv. o Especial
    r"(?:de\s+)?"
    r"Arrend(?:\.|amiento)"                # Arrend. / Arrendamiento
    r"(?:\s+Oral)?"
    r")"
    r"\s*"
    r"T\.\s*(?P<serie>[A-Za-z]{1,4})?\s*"
    r"(?P<num>\d{1,6})\s*[/\-]\s*(?P<anio>\d{4})\s*[/\-]\s*(?P<cons>\d{3})",
    re.IGNORECASE
)

@dataclass
class ParserState:
    last_sala_civil: Optional[str] = None

RE_ORDINAL = re.compile(r"\b(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA)\b", re.IGNORECASE)
RE_SOLO_SALA_CIVIL = re.compile(r"^\s*SALA\s+CIV(?:IL|ÍVIL|IL)\s*$", re.IGNORECASE)

def _enriquecer_sala(m: re.Match, text: str) -> str:
    raw = _clean_chunk(m.group(0))

    # Si ya trae ordinal, úsala tal cual (limpia)
    if RE_ORDINAL.search(raw):
        return raw

    # Si es solo "SALA CIVIL", intenta recuperar el ordinal mirando hacia atrás
    if RE_SOLO_SALA_CIVIL.match(raw):
        ctx = text[max(0, m.start() - 200): m.start()]  # ventana previa
        ords = list(RE_ORDINAL.finditer(ctx))
        if ords:
            ordw = ords[-1].group(1).upper()
            return f"{ordw} SALA CIVIL"

    return raw

def actualizar_ultima_sala(text: str, state: ParserState) -> None:
    last_val = None

    for m in RE_SALA_CIVIL.finditer(text):
        val = _enriquecer_sala(m, text)

        # ✅ No sobre-escribas una sala específica con "SALA CIVIL" genérico
        if (state.last_sala_civil
            and RE_SOLO_SALA_CIVIL.match(val)
            and not RE_SOLO_SALA_CIVIL.match(state.last_sala_civil)):
            continue

        last_val = val

    if last_val:
        state.last_sala_civil = last_val

RE_VS = re.compile(r"\bvs\.?\b", re.IGNORECASE)
RE_ARR = re.compile(r"\bArrend(?:\.|amiento)\b", re.IGNORECASE)

# Solo aceptamos tipos completos (si no está completo -> se omite)
RE_TIPO_ARR_ANY = re.compile(
    r"(?P<tipo>\b(?:Especial|Controv)\.?\s*(?:de\s+)?Arrendamiento(?:\s+Oral)?\b)",
    re.IGNORECASE
)

# ITEM dentro del caso: (tipo arrendamiento) + T. + (pref opcional) + expediente roto (espacios/saltos)
RE_ARR_ITEM_OCR = re.compile(
    r"(?P<tipo>(?:Especial|Controv)\.?\s*(?:de\s+)?Arrendamiento(?:\s+Oral)?)"
    r"\s*"
    r"T\.?\s*"
    r"(?P<pref>[A-Za-z]{1,3})?\s*"
    r"(?P<num>\d(?:\s*\d){0,5})\s*(?:[/\-]|\s)\s*"
    r"(?P<anio>\d(?:\s*\d){3})\s*(?:[/\-]|\s)\s*"
    r"(?P<seq>\d(?:\s*\d){0,2})",
    re.IGNORECASE
)

RE_SENT = re.compile(r"\bSent\.?\b", re.IGNORECASE)
RE_ACDO = re.compile(r"\b(\d{1,3})\s*(acdos?|acdo)\.?\b", re.IGNORECASE)

RE_CASE_TERMINATOR = re.compile(
    r"(?:\bSent\.?\b|\b\d{1,3}\s*(?:Acdos?|Acdo)\.?\b|\bNo\s+Publ(?:icado|\.?)\b)",
    re.IGNORECASE
)

# ✅ Sala civil (tolerante OCR)
RE_SALA_CIVIL = re.compile(
    r"\b(?:(?:PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA)\s+)?SALA\s+CIV(?:IL|\.|ÍVIL)\b",
    re.IGNORECASE
)

# Une expedientes partidos por salto de línea
RE_EXP_SALTO = re.compile(r"(\d{1,6}\s*[/\-]\s*\d{4}\s*[/\-])\s*\n\s*(\d{1,3}\b)")


def _clean_chunk(s: str) -> str:
    if s is None:
        return ""
    s = s.replace("\r", "\n")
    s = re.sub(r"\n+", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return s.strip()


def _normalize_keep_newlines_ocr(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _compact_digits(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _unir_expedientes_partidos(text: str) -> str:
    return RE_EXP_SALTO.sub(r"\1\2", text)


def _case_start_before_vs_ocr(text: str, vs_start: int, lookback: int = 1800) -> int:
    w0 = max(0, vs_start - lookback)
    prefix = text[w0:vs_start]

    last = None
    for m in RE_CASE_TERMINATOR.finditer(prefix):
        last = m
    if last:
        return w0 + last.end()

    idx = prefix.rfind("\n\n")
    if idx != -1:
        return w0 + idx + 2

    idx = prefix.rfind("\n")
    if idx != -1:
        return w0 + idx + 1

    return w0


def _safe_case_start(text: str, vs_start: int, start: int) -> int:
    actor_seg = text[start:vs_start]
    m_all = list(RE_VS.finditer(actor_seg))
    if not m_all:
        return start

    last_vs = m_all[-1]
    after_last_vs = actor_seg[last_vs.end():]
    cut = after_last_vs.rfind("\n")
    if cut != -1:
        return start + last_vs.end() + cut + 1

    return start + last_vs.end()


# ✅ índice de salas: posiciones + valores
def _build_sala_index(text: str):
    matches = list(RE_SALA_CIVIL.finditer(text))
    starts = [m.start() for m in matches]
    values = [m.group(0).strip() for m in matches]
    return starts, values


def _sala_para_pos(starts, values, pos: int) -> Optional[str]:
    # equivalente a bisect_left sin import extra (N pequeño normalmente)
    i = 0
    while i < len(starts) and starts[i] < pos:
        i += 1
    i -= 1
    return values[i] if i >= 0 else None

def parse_arrendamiento_block(
    block: str,
    fecha_pub: str,
    num_boletin: int,
    num_pag: int,
    state: ParserState
) -> List[Dict]:

    text = _normalize_keep_newlines_ocr(block)
    text = _unir_expedientes_partidos(text)

    # ✅ actualiza estado con la sala si aparece en esta página
    actualizar_ultima_sala(text, state)

    if not RE_ARR.search(text):
        return []

    resultados: List[Dict] = []
    seen = set()

    # index de salas en la página (si hay)
    sala_starts, sala_values = _build_sala_index(text)

    vs_all = list(RE_VS.finditer(text))
    if not vs_all:
        return []

    for i, vs_m in enumerate(vs_all):
        case_start = _case_start_before_vs_ocr(text, vs_m.start())
        case_start = _safe_case_start(text, vs_m.start(), case_start)

        case_end = vs_all[i + 1].start() if (i + 1) < len(vs_all) else len(text)
        caso = text[case_start:case_end].strip()

        if not caso or not RE_ARR.search(caso):
            continue

        vs_rel_start = vs_m.start() - case_start
        vs_rel_end = vs_m.end() - case_start
        if vs_rel_start < 0 or vs_rel_end > len(caso):
            continue

        actor_raw = caso[:vs_rel_start]
        resto = caso[vs_rel_end:]

        m_tipo0 = RE_TIPO_ARR_ANY.search(resto)
        if not m_tipo0:
            continue

        if RE_VS.search(resto[:m_tipo0.start()]):  # mezcla => omitimos
            continue

        actor = _clean_name_chunk(_strip_headers(actor_raw)) or None
        demandado = _clean_name_chunk(resto[:m_tipo0.start()]) or None

        # ✅ sala por posición (si está en la página), si no, usa la última guardada
        tipo_abs_pos = case_start + vs_rel_end + m_tipo0.start()
        # sala_civil = _sala_para_pos(sala_starts, sala_values, tipo_abs_pos)
        # if not sala_civil:
        #     sala_civil = state.last_sala_civil  # fallback
        sala_civil = _sala_para_pos(sala_starts, sala_values, tipo_abs_pos)

        # Si la sala encontrada es genérica, usa la del estado si es más específica
        if sala_civil and RE_SOLO_SALA_CIVIL.match(sala_civil) and state.last_sala_civil and not RE_SOLO_SALA_CIVIL.match(state.last_sala_civil):
            sala_civil = state.last_sala_civil

        # Si no hay sala en página, usa estado
        if not sala_civil:
            sala_civil = state.last_sala_civil

        for it in RE_ARR_ITEM_OCR.finditer(resto):
            tipo_juicio = _clean_chunk(it.group("tipo"))
            pref = (it.group("pref") or "").strip()

            num = _compact_digits(it.group("num"))
            anio = _compact_digits(it.group("anio"))
            seq = _compact_digits(it.group("seq")).zfill(3)

            id_expediente = f"T. {pref} {num}/{anio}/{seq}" if pref else f"T. {num}/{anio}/{seq}"

            tail = resto[it.end(): it.end() + 180]
            estatus, num_estatus = None, None
            if RE_SENT.search(tail):
                estatus = "Sent"
            else:
                m_ac = RE_ACDO.search(tail)
                if m_ac:
                    num_estatus = int(m_ac.group(1))
                    estatus = "Acdo"

            reg = {
                "id_expediente": id_expediente,
                "actor_demandante": actor,
                "demandado": demandado,
                "tipo_juicio": tipo_juicio,
                "estatus": estatus,
                "num_estatus": num_estatus,
                "fecha_publicacion": fecha_pub,
                "numero_boletin": num_boletin,
                "numero_pagina": num_pag,
                "sala": sala_civil,  # ✅ ya no se pierde
            }

            key = (
                reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
                reg["tipo_juicio"], reg["estatus"], reg["num_estatus"],
                reg["sala"], reg["fecha_publicacion"], reg["numero_boletin"], reg["numero_pagina"]
            )
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

