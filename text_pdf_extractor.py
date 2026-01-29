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
RE_TIPO_OBJETIVO = re.compile(
    r"(?P<tipo>"
    r"(?:"
    r"(?:Controv\.?\s*(?:de\s*)?Arrend(?:\.|amiento)?)"
    r"|(?:Cnpcyf\s*-\s*Especial\s*de\s*Arrendamiento\s*Oral)"
    r"|(?:Especial\s*de\s*Arrendamiento\s*Oral)"
    r"|(?:Arrend\.?)"
    r"|(?:Ejec\.?\s*Merc\.?)"         # ✅ NUEVO
    r"|(?:Ejec\s*Merc\.?)"           # ✅ OCR: sin punto
    r")"
    r")",
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

# Palabras que indican que la coma NO separa demandados (es “descripción” corporativa)
_DEMANDADO_NO_SPLIT_AFTER = {
    "institucion", "institución", "institucien", "institucién",
    "grupo", "financiero", "division", "división", "fiduciaria",
    "como", "fiduciario", "fideicomiso", "identificado", "identificada",
    "con", "numero", "número", "del", "de", "la", "el", "en", "entidad",
    "objeto", "multiple", "múltiple", "regulada", "no", "publicado", "publicada"
}

# Tokens “ruido” tipo "y Otra"
_RE_OTRO = re.compile(r"(?i)^(?:otr[oa]s?)\.?$")

# Frases de alias: corta todo lo que venga DESPUÉS
_ALIAS_SPLITS = [
    r"(?i)\bquien\s+tamb[ií]en\s+se\s+ostenta\b",
    r"(?i)\bquien\s+tamb[ií]en\s+se\s+ostenta\s+como\b",
    r"(?i)\bquien\s+tamb[ií]en\s+acostumbra\s+usar\b",
    r"(?i)\bquien\s+tamb[ií]en\s+acostumbra\s+usar\s+el\s+nombre\b",
    r"(?i)\btambi[eé]n\s+conocid[oa]\s+como\b",
    r"(?i)\banteriormente\s+conocid[oa]\s+como\b",
]

# Split por "y/e" SOLO si después parece iniciar otro demandado (Mayúscula o comilla)
RE_Y_SPLIT = re.compile(r"(?i)\s+\b(?:y|e)\b\s+(?=[\"“”A-ZÁÉÍÓÚÑ])")

# Tokens tipo "y Otra", "y Otros", etc.
RE_OTRO_TOKEN = re.compile(r"(?i)^(?:y|e)?\s*otr[oa]s?\b\.?$")

def _fix_ocr_broken_initials(s: str) -> str:
    """
    Une letra MAYÚSCULA suelta + palabra en minúscula (OCR):
      'E varisto' -> 'Evaristo'
    y limpia basura típica ' n ' / ' l ' suelta que aparece en corporativos.
    """
    if not s:
        return s

    # Une "E varisto" -> "Evaristo" (solo si la 2a parte tiene 2+ letras)
    s = re.sub(r"\b([A-ZÁÉÍÓÚÑ])\s+([a-záéíóúñ]{2,})\b", r"\1\2", s)

    # Quita tokens basura sueltos: " n " / " l " antes de mayúscula (en el Fideicomiso / el ...)
    s = re.sub(r"(?<=\s)[nl]\s+(?=[A-ZÁÉÍÓÚÑ])", "", s)

    return s

def _cut_alias_phrases(s: str) -> str:
    """
    Corta todo lo que venga después de frases alias tipo:
    - "Quien también se ostenta como ..."
    - "Quien también utiliza/utliza/usa/acostumbra usar el nombre ..."
    - "También conocido como ..."
    - "Anteriormente conocido como ..."
    """
    if not s:
        return s

    patterns = [
        r"(?i)\bquien\s+tamb[ií]en\s+se\s+ostent[ae]\b",
        r"(?i)\bquien\s+tamb[ií]en\s+(?:utiliz[ae]|utliza|usa|acostumbr[ae]\s+usar)\b",
        r"(?i)\bquien\s+(?:tamb[ií]en\s+)?(?:utiliz[ae]|utliza|usa|acostumbr[ae]\s+usar)\s+(?:el\s+)?nombre\b",
        r"(?i)\b(?:tamb[ií]en\s+)?conocid[oa]\s+como\b",
        r"(?i)\banteriormente\s+conocid[oa]\s+como\b",
        r"(?i)\bquien\s+tamb[ií]en\s+utiliza\b",
        r"(?i)\bquien\s+tamb[ií]en\s+utliza\b",
    ]

    out = s
    for pat in patterns:
        out = re.split(pat, out, maxsplit=1)[0].strip()

    return out

def _promote_party_commas_to_semicolon(s: str) -> str:
    """
    Convierte ciertas comas en ';' SOLO cuando parecen separar demandados.
    No rompe: '..., S.A., Institución de ...'
    Sí separa: '..., C.V., Márquez Meza Rubén ...'
    """
    def repl(m: re.Match) -> str:
        word = m.group(1) or ""
        wl = word.lower()
        if wl in _DEMANDADO_NO_SPLIT_AFTER:
            return m.group(0)  # conserva coma
        # no separar si el “word” es un sufijo corporativo típico
        if re.match(r"(?i)^(s\.?a\.?p?i?\.?|sa|s\.?\s*de|sc|s\.?c\.?|a\.?c\.?m\.?)$", word):
            return m.group(0)
        return "; "  # esta coma sí separa demandados

    return re.sub(r",\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ]+)\b", repl, s)

# ==========================
# DEMANDADOS: split + alias
# ==========================

# Tokens corporativos / continuaciones donde NO queremos partir por comas
_RE_CORP_HINT = re.compile(
    r"(?i)\b(?:S\.?\s*A\.?|C\.?\s*V\.?|S\.?\s*de\s*R\.?\s*L\.?|S\.?\s*N\.?\s*C\.?|"
    r"SOFOM|INSTITUCI[OÓ]N|BANCA|FIDUCIARI[OA]|FIDEICOMISO|DIVISI[OÓ]N|SOCIEDAD|GRUPO|"
    r"FINANCIER[OA]|FIDEICOMIS[OA])\b"
)

# Palabras basura que salen cuando accidentalmente se corta una línea ("n", "l", "en", etc.)
_RE_DEMANDADO_NOISE = re.compile(r"(?i)^(?:n|l|el|la|los|las|en|del|de|al)$")

# Token genérico para "Otro(s)/Otra(s)" cuando queda solo
_RE_OTRO_PDF = re.compile(r"(?i)^(?:otr[oa]s?)\.?$")

def _cut_alias_phrases_pdf(s: str) -> str:
    """Corta el demandado en cuanto aparece un alias / 'también conocido...' etc."""
    if not s:
        return s

    # Variantes OCR comunes: "utliza/utiza" (pierde la i), "tambien/también", etc.
    patterns = [
        r"\bquien\s+tambi[eé]n\s+utiliza\b",
        r"\bquien\s+tambi[eé]n\s+utliza\b",
        r"\bquien\s+tambi[eé]n\s+utiza\b",
        r"\bquien\s+tambi[eé]n\s+usa\b",
        r"\bquien\s+tambi[eé]n\s+se\s+ostenta\s+como\b",
        r"\bquien\s+tambi[eé]n\s+se\s+ostenta\s+con\s+el\s+nombre\s+de\b",
        r"\btambi[eé]n\s+conocid[oa]\s+como\b",
        r"\btambi[eé]n\s+identificad[oa]\s+como\b",
        r"\b(antes|anteriormente)\s+conocid[oa]\s+como\b",
        r"\bquien\s+tambi[eé]n\s+acostumbra\s+usar\b",
        r"\bquien\s+tambi[eé]n\s+se\s+autodenomina\b",
        r"\bquien\s+tambi[eé]n\s+se\s+denomina\b",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if m:
            return s[:m.start()].strip(" ,.;:-")
    return s


    patterns = [
        r"(?i)\bquien\s+tamb[ií]en\s+(?:se\s+ostenta|utiliza|utliza|usa|acostumbra\s+usar|acostumbra\s+utilizar)\b",
        r"(?i)\b(?:anteriormente\s+)?conocid[oa]\s+como\b",
        r"(?i)\btambi[eé]n\s+conocid[oa]\s+como\b",
        r"(?i)\b(?:usa|utiliza|utliza)\s+el\s+nombre\s+de\b",
        r"(?i)\bquien\s+tamb[ií]en\b",  # fallback amplio
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            s = s[:m.start()].strip()
    return s

def _join_dropped_initials_pdf(s: str) -> str:
    """Une casos OCR del tipo 'E varisto' -> 'Evaristo'"""
    if not s:
        return ""
    return re.sub(r"\b([A-ZÁÉÍÓÚÑ])\s+([a-záéíóúñ]{2,})\b", r"\1\2", s)

def _promote_party_commas_to_semicolon_pdf(s: str) -> str:
    """Convierte COMAS que separan demandados (personas) a ';' sin romper comas internas corporativas."""
    if not s:
        return ""
    out = []
    last = 0
    for m in re.finditer(r",\s+(?=[A-ZÁÉÍÓÚÑ])", s):
        prev = s[max(0, m.start() - 40): m.start()]
        nxt = s[m.end(): m.end() + 30]

        # Si cerca del separador hay indicios corporativos, NO partir
        if _RE_CORP_HINT.search(prev) or re.match(
            r"(?i)(?:S\.?\s*A\.?|C\.?\s*V\.?|INSTITUCI[OÓ]N|DIVISI[OÓ]N|SOFOM|BANCA|GRUPO)\b", nxt
        ):
            continue

        out.append(s[last:m.start()])
        out.append("; ")
        last = m.end()

    out.append(s[last:])
    return "".join(out)

def split_demandados_pdf(demandado_raw: str) -> List[str]:
    """
    Separa demandados (PDF) de forma robusta y compatible con tu extractor OCR:

    - Corta alias: 'Quien también...', 'También conocido...', etc.
    - Corrige OCR pegado: 'yBravo' -> 'y Bravo'
    - Evita falsos splits por 'en/el' roto como 'e n e l' (bug por IGNORECASE en lookahead)
    - Separa por ';' y por 'y/e' SOLO cuando el siguiente token parece iniciar un nombre/entidad (mayúscula/“comillas”)
    - Convierte comas a ';' solo cuando la coma realmente separa demandados (no corporativos)
    - Elimina 'y Otro(s)/Otra(s)' al final
    """
    s = _clean_chunk(demandado_raw) if demandado_raw else ""
    s = (s or "").strip()
    if not s:
        return []

    # 1) Alias / también conocido
    s = _cut_alias_phrases_pdf(s)

    # 2) Reparar OCR pegado: "yBravo" -> "y Bravo" (y también "eEmpresa" -> "e Empresa")
    s = re.sub(r"(?i)\b([ye])(?=[A-ZÁÉÍÓÚÑ])", r"\1 ", s)

    # 3) 'y Otros/Otras' al final no es un demandado
    s = re.sub(r"\s+(?:y|e)\s+otr[oa]s?\b\.?$", "", s, flags=re.IGNORECASE).strip()

    # 4) Unir inicial perdida: "E varisto" -> "Evaristo" (evita que luego se dropee la 'E')
    s = _join_dropped_initials_pdf(s)

    # 5) Arreglos mínimos de stopwords rotos típicos: "e n e l" -> "en el", "e l" -> "el"
    #    (esto reduce ruido y evita que el split por 'e' se dispare)
    s = re.sub(r"(?i)\be\s+n\s+e\s+l\b", "en el", s)
    s = re.sub(r"(?i)\be\s+l\b", "el", s)
    s = re.sub(r"(?i)\be\s+n\b", "en", s)

    # 6) Si parece corporativo, recorta colas de fideicomiso/fiduciario (no son 'otro demandado')
    if re.search(r"(?i)\b(S\.?\s*A\.?|S\.?\s*de\s*C\.?V\.?|C\.?V\.?|Banco|Instituci[oó]n|Sofom|Fiduciari[ao]|Divisi[oó]n\s+Fiduciaria)\b", s):
        m_tail = re.search(
            r"(?i)\b(?:como\s+fiduciari[ao]|en\s+el\s+fideicomiso|fideicomiso\s+identificado|identificado\s+con|identificado\s+como|con\s+el\s+n[uú]mero|n[uú]mero\s+[A-Z0-9/.-]{2,})\b",
            s,
        )
        if m_tail:
            s = s[:m_tail.start()].strip(" ,.;:-")

    # 7) Comas que realmente separan demandados -> ';'
    s = _promote_party_commas_to_semicolon_pdf(s)

    # 8) Split fuerte por ';'
    parts = [p.strip() for p in re.split(r"\s*;\s*", s) if p.strip()]

    out: List[str] = []
    seen = set()

    for part in parts:
        part = _cut_alias_phrases_pdf(part)
        part = part.strip(" .,-;:")

        if not part:
            continue

        # ✅ Split por ' y ' / ' e ' SOLO si lo que sigue parece iniciar un nombre/entidad.
        # Importante: el lookahead debe ser *case-sensitive*; por eso NO usamos (?i) global.
        subparts = re.split(r"\s+(?i:(?:y|e))\s+(?=[\"“”A-ZÁÉÍÓÚÑ])", part)

        for sp in subparts:
            sp = _cut_alias_phrases_pdf(sp)
            sp = _clean_chunk(sp) if sp else ""
            sp = (sp or "").strip(" .,-;:")

            # ruido típico que queda suelto (n, l, el, de, etc.)
            if not sp or _RE_DEMANDADO_NOISE.match(sp):
                continue
            if _RE_OTRO.match(sp):
                continue

            key = sp.lower()
            if key not in seen:
                seen.add(key)
                out.append(sp)

    return out


    # Normaliza pegados: "yBravo" -> "y Bravo"
    s = re.sub(r"(?i)\b([ye])(?=[A-ZÁÉÍÓÚÑ])", r"\1 ", s)

    # Corta alias global
    s = _cut_alias_phrases_pdf(s)

    # Quita cola " y Otro(s)/Otra(s)/Otros"
    s = re.sub(r"\s+(?:y|e)\s+otr[oa]s?\b\.?$", "", s, flags=re.IGNORECASE).strip()

    # Coma separador de personas => ';'
    s = _promote_party_commas_to_semicolon_pdf(s)

    # Split fuerte por ';'
    parts = [p.strip() for p in re.split(r"\s*;\s*", s) if p.strip()]

    out: List[str] = []
    seen = set()

    for part in parts:
        part = _cut_alias_phrases_pdf(part)
        part = _join_dropped_initials_pdf(part).strip(" .,-;:")
        if not part:
            continue

        # Split por ' y ' / ' e ' SOLO si lo que sigue parece iniciar un nombre/entidad
        subparts = re.split(r"(?i)\s+(?:y|e)\s+(?=[\"“”A-ZÁÉÍÓÚÑ])", part)

        for sp in subparts:
            sp = _cut_alias_phrases_pdf(sp)
            sp = _join_dropped_initials_pdf(sp)
            sp = (_clean_chunk(sp) or "").strip(" .,-;:")

            if not sp:
                continue
            if _RE_DEMANDADO_NOISE.match(sp):
                continue
            if _RE_OTRO_PDF.match(sp):
                continue

            key = sp.lower()
            if key not in seen:
                seen.add(key)
                out.append(sp)

    return out

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

        # ✅ Partir actor/resto usando el vs_m real
        vs_rel_start = vs_m.start() - case_start
        vs_rel_end = vs_m.end() - case_start

        if vs_rel_start < 0 or vs_rel_end > len(caso):
            continue

        actor_raw = caso[:vs_rel_start]
        resto = caso[vs_rel_end:]

        # Ubicar primer T.
        mt = RE_T_DOT.search(resto)
        if not mt:
            continue

        # ✅ VALIDACIÓN CLAVE:
        arr_rel = arr_pos - case_start
        t_rel = vs_rel_end + mt.start()
        if not (vs_rel_end < arr_rel < t_rel):
            continue

        before_t = _clean_chunk(resto[:mt.start()])  # demandado + tipo
        from_t = resto[mt.start():]                  # desde T. en adelante

        # ✅ Otra validación: Arrend debe estar ANTES del T. en el tramo previo
        if not RE_ARR.search(before_t):
            continue

        # Tipo/demandado (Controv. Arrend.)
        tipo_juicio: Optional[str] = None
        demandado_raw = before_t

        tipo_m = None
        tipo_matches = list(RE_TIPO_OBJETIVO.finditer(before_t))  # ✅ incluye Ejec. Merc

        if tipo_matches:
            tipo_m = tipo_matches[-1]

        if tipo_m:
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

        # ✅ NUEVO: separar demandados + limpiar alias ("Quien también...", "y Otra(s)", etc.)
        demandados = split_demandados_pdf(demandado_raw)
        if not demandados:
            demandados = [demandado_raw or None]

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

        # ✅ NUEVO: mapea demandado -> índice incremental ("demandado: 1", ...)
        #      único por demandado dentro del caso (para no repetir por errores OCR)
        dem_index = {}
        idx = 1
        for d in demandados:
            k = (d or "").strip().lower()
            if k and k not in dem_index:
                dem_index[k] = idx
                idx += 1

        for exp in expedientes:
            for idx_dem, dem in enumerate(demandados, start=1):
                reg = {
                    "id_expediente": exp,
                    "actor_demandante": actor or None,
                    "demandado": dem,
                    "tipo_juicio": tipo_juicio,
                    "estatus": estatus,
                    "num_estatus": num_estatus,
                    "fecha_publicacion": fecha_pub,
                    "numero_boletin": num_boletin,
                    "numero_pagina": pagina_caso if pagina_caso is not None else pagina_final,
                    "sala": sala_civil,
                    "conteo_demandados": f"demandado: {idx_dem}",
                }

                key = (
                    reg["id_expediente"], reg["actor_demandante"], reg["demandado"],
                    reg["tipo_juicio"], reg["estatus"], reg["fecha_publicacion"], reg["numero_boletin"],
                    reg["numero_pagina"], reg["sala"], reg["conteo_demandados"],
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