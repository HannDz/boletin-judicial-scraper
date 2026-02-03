import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import defaultdict

_DASH = r"[-–—]"

RE_EXP = re.compile(
    rf"\bT\.?\s*(?:(?P<pref>[A-Za-z]{{1,4}})\.?\s*)?"
    rf"(?P<num>\d{{1,5}})\s*"
    rf"(?:"
      rf"(?:/|\s+)\s*(?P<anio_slash>\d{{4}})\s*(?:/|\s+)\s*(?P<seq_slash>\d{{1,3}})"
      rf"|{_DASH}\s*(?P<anio_h>\d{{3,4}})(?:\s*{_DASH}\s*(?P<seq_h>\d{{1,3}}))?"
    rf")",
    re.IGNORECASE
)

def _fix_year_ocr(year: str) -> str:
    y = (year or "").strip()
    # OCR típico: 2021 -> 201, 2022 -> 202, 2023 -> 203
    if len(y) == 3 and y.startswith("20") and y[2].isdigit():
        return "202" + y[2]
    return y

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

RE_TIPO = re.compile(
    r"(?P<tipo>"
    r"(?:\w{2,15}\s*[-–—]\s*)?"                       # prefijo opcional: Cnpeyf-
    r"(?:Controv\.?\s*(?:de\s+)?Arrend(?:\.|amiento)" # Controv Arrend
    r"|Especial\s*de\s*Arrendamiento\s*Oral"          # Especial Arrend Oral
    r"|Ejec\.?\s*Merc\.?)"                            # Ejec Merc
    r")(?=\W|$)",
    re.IGNORECASE
)

RE_TIPO_CASO = re.compile(
    r"(Controv\.?\s*(?:de\s+)?Arrend(?:\.|amiento)"
    r"|Ejec\.?\s*Merc\.?)",
    re.IGNORECASE
)


# Solo aceptamos tipos completos (si no está completo -> se omite)
RE_TIPO_ARR_ANY = re.compile(
    r"(?P<tipo>\b(?:\w{2,20}\s*[-–—]\s*)?(?:Especial|Controv)\.?\s*(?:de\s+)?Arrend(?:\.|amiento)(?:\s+Oral)?\b)",
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

# ✅ tolerante a OCR: "instituci..." cubre Institución / Institucien / Institucién / Institucion
# y lo mismo con divisi..., fiduci..., fideicomis...
DESCRIPTORES_POST_SUF = (
    r"(?:"
    r"instituci\w*|"
    r"divisi\w*|"
    r"grupo|financier\w*|"
    r"fiduci\w*|"
    r"fideicomis\w*|"
    r"administraci\w*|direcci\w*|"
    r"como|"
    r"ord|ejec|esp|juris|controv|incid|cuad|amp|expdlo"
    r")\b"
)

def _join_dropped_initials(s: str) -> str:
    """
    Repara casos OCR tipo: 'E spejel' -> 'Espejel'
    Solo une si: 1 letra + espacio + palabra en minúsculas (>=3 letras)
    """
    return re.sub(
        r"\b([A-ZÁÉÍÓÚÑ])\s+([a-záéíóúñ]{3,})\b",
        lambda m: m.group(1) + m.group(2),
        s
    )

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

    # Si no hay tipo objetivo (Arrend o Ejec. Merc.), salimos
    # (fallback: si OCR rompe el match del tipo pero sí aparece 'Arrend')
    if not (RE_TIPO.search(text)):
        return []


    resultados: List[Dict] = []
    seen = set()

    # index de salas en la página (si hay)
    sala_starts, sala_values = _build_sala_index(text)

    vs_all = list(RE_VS.finditer(text))
    if not vs_all:
        return []

    def _fmt_exp_from_match(m: re.Match) -> str:
        pref = (m.group("pref") or "").strip()
        num  = (m.group("num") or "").strip()

        if m.group("anio_slash"):
            anio = (m.group("anio_slash") or "").strip()
            seq  = (m.group("seq_slash") or "").strip().zfill(3)
            return (f"T. {pref} {num}/{anio}/{seq}".strip() if pref else f"T. {num}/{anio}/{seq}")
        else:
            anio = _fix_year_ocr(m.group("anio_h"))
            seq  = m.group("seq_h")
            if seq:
                return f"T. {num}-{anio}-{seq.strip().zfill(3)}"
            return f"T. {num}-{anio}"

    for i, vs_m in enumerate(vs_all):
        case_start = _case_start_before_vs_ocr(text, vs_m.start())
        case_start = _safe_case_start(text, vs_m.start(), case_start)

        case_end = vs_all[i + 1].start() if (i + 1) < len(vs_all) else len(text)
        caso = text[case_start:case_end].strip()

        # ✅ si no hay Arrend en el caso, no lo proceses
        if not caso or not RE_TIPO.search(caso):
            continue

        vs_rel_start = vs_m.start() - case_start
        vs_rel_end = vs_m.end() - case_start
        if vs_rel_start < 0 or vs_rel_end > len(caso):
            continue

        actor_raw = caso[:vs_rel_start]
        resto = caso[vs_rel_end:]

        # ✅ Tipo completo (Especial/Controv + Arrend. / Arrendamiento)
        m_tipo0 = RE_TIPO.search(resto)
        if not m_tipo0:
            continue

        # ✅ Si antes del tipo aparece otro "vs", es mezcla => omite
        if RE_VS.search(resto[:m_tipo0.start()]):
            continue

        actor = _clean_name_chunk(_strip_headers(actor_raw)) or None

        # Demandado(s)
        demandado_raw = _clean_name_chunk(resto[:m_tipo0.start()]) or ""
        demandados = split_demandados(demandado_raw)
        if not demandados:
            continue

        # Mapa estable: demandado -> índice incremental (1..N) por caso (NO por expediente)
        idx_map = {d: i + 1 for i, d in enumerate(demandados)}


        # ✅ sala por posición (si está en la página), si no, usa la última guardada
        tipo_abs_pos = case_start + vs_rel_end + m_tipo0.start()
        sala_civil = _sala_para_pos(sala_starts, sala_values, tipo_abs_pos)

        # Si la sala encontrada es genérica, usa la del estado si es más específica
        if (sala_civil and RE_SOLO_SALA_CIVIL.match(sala_civil)
                and state.last_sala_civil
                and not RE_SOLO_SALA_CIVIL.match(state.last_sala_civil)):
            sala_civil = state.last_sala_civil

        if not sala_civil:
            sala_civil = state.last_sala_civil

        tipo_juicio = _clean_chunk(m_tipo0.group("tipo"))

        # ✅ en vez de RE_ARR_ITEM_OCR, extrae expedientes robusto (2023 incluido)
        segmento = resto[m_tipo0.start():]
        exp_matches = list(RE_EXP.finditer(segmento))
        if not exp_matches:
            # si no hay expediente, omitimos (estructura incompleta)
            continue

        for em in exp_matches:
            id_expediente = _fmt_exp_from_match(em)

            tail = segmento[em.end(): em.end() + 220]
            estatus, num_estatus = None, None
            if RE_SENT.search(tail):
                estatus = "Sent"
            else:
                m_ac = RE_ACDO.search(tail)
                if m_ac:
                    num_estatus = int(m_ac.group(1))
                    estatus = "Acdo"

            for demandado in demandados:
                conteo_demandados = f"demandado: {idx_map[demandado]}"
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

                    # ✅ mantén ambos para no perderlo
                    "sala": sala_civil,
                    "juzgado": sala_civil,
                    "conteo_demandados": conteo_demandados,
                }

                key = (
                    reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
                    reg["tipo_juicio"], reg["estatus"], reg["num_estatus"],
                    reg["sala"], reg["fecha_publicacion"], reg["numero_boletin"], reg["numero_pagina"], reg["conteo_demandados"]
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
        if not (RE_TIPO.search(chunk)):
            continue


        regs = parse_arrendamiento_block(chunk)
        for r in regs:
            key = (r.get("id_expediente"), r.get("actor_demandante"), r.get("demandado"), r.get("tipo_juicio"), r.get("estatus"))
            if key not in seen:
                seen.add(key)
                results.append(r)

    return results

def enumerar_demandados_por_expediente(registros: List[Dict]) -> List[Dict]:
    """
    Asigna conteo_demandados = "demandado: N" (N incremental) para demandados únicos por id_expediente.
    - Si un demandado se repite en el mismo expediente, conserva el mismo N.
    - Orden por primera aparición.
    """
    idx_map = defaultdict(dict)              # exp -> { demandado: idx }
    next_idx = defaultdict(lambda: 1)        # exp -> siguiente idx

    for r in registros:
        exp = (r.get("id_expediente") or "").strip()
        dem = (r.get("demandado") or "").strip()

        if not exp or not dem:
            r["conteo_demandados"] = None
            continue

        if dem in idx_map[exp]:
            idx = idx_map[exp][dem]
        else:
            idx = next_idx[exp]
            idx_map[exp][dem] = idx
            next_idx[exp] = idx + 1

        r["conteo_demandados"] = f"demandado: {idx}"

    return registros

# --- CORTES DE "ALIAS" / "SE OSTENTA" / "ACOSTUMBRA USAR NOMBRE" ---
RE_ALIAS_CUT = re.compile(
    r"""
    \b
    (?:quien|qui[eé]n)                # quien / quién
    \s+tamb[ií]en\s+                  # también
    (?:                               # frases típicas
        se\s+ostenta
        |acostumbra\s+usar
        |usa
        |responde
    )
    (?:\s+(?:como|al|a|el|l)\s+nombre\s+de|\s+como|\s+el\s+nombre\s+de|\s+l\s+nombre\s+de)?  # OCR: "l nombre"
    \b
    .*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_CONOCIDO_COMO_CUT = re.compile(
    r"""
    \b
    (?:anteriormente\s+conocid[oa]
      |tamb[ií]en\s+conocid[oa]
      |conocid[oa]
      |identificad[oa]
    )
    \s+como
    \b
    .*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- "y Otra(s) / y Otro(s)" (no debe convertirse en demandado) ---
RE_OTRO_TOKEN = re.compile(r"^(?:y\s+)?otr[oa]s?\.?$", re.IGNORECASE)

# --- Separador por "y/e" entre demandados, SOLO si el siguiente parece nombre (Mayúscula/“") ---
# Solo arregla OCR tipo: yBravo -> y Bravo / eInmobiliaria -> e Inmobiliaria
# PERO solo si lo que sigue es Nombre con mayúscula real + minúscula real (no "en", "el", etc)
RE_YBRAVO_FIX = re.compile(
    r'(?i)\b([ye])(?=(?-i:[A-ZÁÉÍÓÚÑ])[a-záéíóúñ])'
)

# Split por " y " / " e " SOLO si lo que sigue parece nombre real
RE_Y_SPLIT = re.compile(
    r'\s+(?:y|e)\s+(?=(?:["“‘]?\s*)?(?-i:[A-ZÁÉÍÓÚÑ])[a-záéíóúñ])',
    re.IGNORECASE
)

# Corta alias en cuanto aparezca "Quien también ..."
RE_ALIAS_QUIEN_TAMBIEN = re.compile(r'(?i)\bquien\s+tambi[eé]n\b.*$')

# Corta alias: "conocido como", "anteriormente conocido como"
RE_ALIAS_CONOCIDO = re.compile(r'(?i)\b(?:anteriormente\s+)?conocid[oa]\s+como\b.*$')

# Quita cola " y Otro(s)/Otra(s)" al final
RE_OTROS_TAIL = re.compile(r'(?i)\s+y\s+(?:otro|otra|otros|otras)\b.*$')

# --- Sufijos corporativos (tolerante a OCR) ---
_CORP = r"(?:S\.?\s*A\.?|S\.?\s*de\s*R\.?\s*L\.?|A\.?\s*C\.?|S\.?\s*C\.?|SAPI|S\.?\s*A\.?\s*P\.?\s*I\.?|I\.?\s*A\.?\s*P\.?)"
_CORP_TAIL = r"(?:\s*(?:de\s+)?(?:C\.?\s*V\.?|R\.?\s*L\.?))?"
_CORP_SUFFIX = rf"(?:{_CORP}{_CORP_TAIL})"

# No partir por coma cuando lo que sigue es descriptor del MISMO demandado
_CORP_NO_SPLIT_NEXT = r"(?:Instituci[oó]n|Institucion|Divisi[oó]n|Division|Grupo|Financier|Fideicomiso|Fiduciari|como|Notario|P[úu]blico|Director|Gerente)\b"

# Coma “separadora” después de sufijo corporativo, pero NO si sigue descriptor típico
RE_CORP_COMMA_DELIM = re.compile(
    rf"(?P<suf>\b{_CORP_SUFFIX}\b)\s*,\s*(?=(?!{_CORP_NO_SPLIT_NEXT})[A-ZÁÉÍÓÚÑ\"“])",
    re.IGNORECASE,
)

# Palabras que indican que la coma NO separa demandados (son parte del mismo nombre corporativo)
DESCRIPTORES_POST_COMMA = r"(?:Sociedad|An[oó]nima|Instituci[oó]n|Banca|M[uú]ltiple|Grupo|Financier\w*|Fideicomis\w*|Fiduciari\w*|Sofom|Notario|P[úu]blico|Director|Gerente)\b"

# Coma separadora “real” (lista de demandados), SOLO si lo que sigue parece nombre/entidad
# y NO es un descriptor corporativo ni abreviatura tipo S.A., A.C., etc.
RE_COMMA_PARTY_SPLIT = re.compile(
    rf",\s+(?=(?!{DESCRIPTORES_POST_COMMA})"
    rf"(?!S\.?\s*A\.?\b)(?!A\.?\s*C\.?\b)(?!S\.?\s*C\.?\b)"
    rf"(?-i:[A-ZÁÉÍÓÚÑ])[a-záéíóúñ])",
    re.IGNORECASE
)

def _cut_alias_phrases(s: str) -> str:
    if not s:
        return s

    s = RE_ALIAS_QUIEN_TAMBIEN.sub("", s).strip()
    s = RE_ALIAS_CONOCIDO.sub("", s).strip()

    # también corta cosas tipo "su Sucesión" si te conviene (opcional)
    s = re.sub(r"(?i)\s+su\s+sucesi[oó]n\b.*$", "", s).strip()

    # limpia puntitos/espacios finales
    s = re.sub(r"\s{2,}", " ", s).strip(" .;,-")
    return s

def _join_dropped_initials(s: str) -> str:
    """
    Repara OCR tipo:
    'E spejel' -> 'Espejel'
    'e spejel' -> 'Espejel'
    """
    def _fix(m: re.Match) -> str:
        return m.group(1).upper() + m.group(2)
    return re.sub(r"\b([A-Za-zÁÉÍÓÚÑáéíóúñ])\s+([a-záéíóúñ]{3,})\b", _fix, s)

def _clean_name_chunk(s: str) -> str:
    """Tu limpiador actual (si ya lo tienes, NO lo dupliques)."""
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = s.strip(" ,;.")
    return s

def split_demandados(demandado_raw: str) -> List[str]:
    """
    Devuelve lista de demandados:
    - corta 'Quien también ...', '... conocido como ...'
    - ignora 'y Otra(s)/Otro(s)'
    - separa por ';' y por 'y/e' (cuando procede)
    - evita romper corporativos por comas tipo: '..., S.A., Institución de ...'
    """
    s = _clean_name_chunk(demandado_raw)
    if not s:
        return []

    # 1) corta alias a nivel global (por si viene al final del demandado completo)
    s = _cut_alias_phrases(s)

    # 2) ✅ FIX: normaliza OCR "yBravo" -> "y Bravo" / "eInmobiliaria" -> "e Inmobiliaria"
    #    sin romper "en", "el", "Espejel", etc.
    s = RE_YBRAVO_FIX.sub(r"\1 ", s)

    # 3) ✅ elimina cola tipo " y Otra(s)/Otro(s)" pegada al final (antes de split)
    s = RE_OTROS_TAIL.sub("", s).strip()

    # 4) trata ';' como separador fuerte
    parts_semicolon = [p.strip() for p in re.split(r"\s*;\s*", s) if p.strip()]

    out: List[str] = []
    seen = set()

    for p in parts_semicolon:
        p = RE_CORP_COMMA_DELIM.sub(lambda m: f"{m.group('suf')} | ", p)

        p = RE_COMMA_PARTY_SPLIT.sub(" ; ", p)

        p_parts = [x.strip() for x in re.split(r"\s*;\s*", p) if x.strip()]

        for pp in p_parts:
            chunks = [c.strip() for c in pp.split("|") if c.strip()]

            for c in chunks:
                c = _cut_alias_phrases(c)
                c = _join_dropped_initials(c)
                c = _clean_name_chunk(c)

                if not c:
                    continue
                if RE_OTRO_TOKEN.fullmatch(c):
                    continue

                sub = [x.strip() for x in RE_Y_SPLIT.split(c) if x.strip()]
                for q in sub:
                    q = _cut_alias_phrases(q)
                    q = _join_dropped_initials(q)
                    q = _clean_name_chunk(q)

                    if not q:
                        continue
                    if RE_OTRO_TOKEN.fullmatch(q):
                        continue

                    key = q.lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(q)

    return out
