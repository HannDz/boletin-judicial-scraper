# main.py
import os
import json
import traceback
import argparse, time
import requests
from datetime import datetime, date
from pathlib import Path
from scraper import *
from redirection import *
from extractor_js import *
from images import *
from configuration import settings
from repository import *
from text_extractor import *
from text_pdf_extractor import *

def run_once():
    # -----------------------------
    # Configuración de carpetas
    # -----------------------------
    os.makedirs("tmp", exist_ok=True)

    LOG_DIR = Path(settings.log_dir)
    LOG_DIR.mkdir(exist_ok=True)
    LOG_FILE = LOG_DIR / settings.log_file


    def log_error_boletin(
        fecha_boletin: date,
        url_boletin: str,
        etapa: str,
        exc: Exception,
        extra: dict | None = None
    ) -> None:
        """
        Guarda error a archivo SIN tronar el proceso.
        Incluye: timestamp, fecha del boletín, URL, etapa, excepción, traceback.
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "timestamp": ts,
            "fecha_boletin": str(fecha_boletin),
            "url_boletin": url_boletin,
            "etapa": etapa,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc()
        }
        if extra:
            payload["extra"] = extra

        # Log legible (JSON por línea)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


    # -----------------------------
    # Sesión
    # -----------------------------
    session = crear_sesion()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    URL_Boletin = settings.url_boletin
    debug = settings.is_debbug

    html2 = obtener_html_filtrado(
        settings.url_boletin_filtro,
        URL_Boletin,
        settings.fecha_ini,
        settings.fecha_fin
    )

    externos = extraer_externos(html2, settings.is_debbug)
    state = ParserState()

    # -----------------------------
    # Loop principal: 1 try/except POR BOLETÍN
    # -----------------------------
    for fecha, l in externos:
        try:
            if existe_procesamiento(fecha, l):
                print(f"Ya existe {l}")
                continue

            expedientes = []
            textos: list[str] = []
            cantidad_insercion = 0
            contador = 0

            # intenta obtener redirect al visor
            direccion = extraer_url_redireccion(html=obtener_html(l))

            # =============================
            # Rama A) VISOR / IMÁGENES
            # =============================
            if direccion is not None:
                try:
                    html = requests.get(direccion, timeout=60).text
                    resultado = extraer_paginas_js(html)
                except Exception as e_dir:
                    log_error_boletin(fecha, l, "Obtener páginas JS del visor", e_dir, {"direccion": direccion})
                    continue

                contador = 1
                fecha_pub: date | None = None
                num_boletin: int | None = None
                inicio_columnas: int | None = None

                for p in resultado:
                    try:
                        html_thumb = session.get(p["thumb"]).text 
                        print(f"OCR página {contador} -> {html_thumb}")

                        if contador == 1:
                            texto = procesar_pagina(session, html_thumb, contador)
                            inicio_columnas = obtener_inicio_columnas(texto)
                            fecha_pub, num_boletin = extraer_fecha_y_numero_boletin(texto)

                        elif inicio_columnas is not None and inicio_columnas <= contador:
                            texto = procesar_pagina_columna(session, html_thumb, contador)
                            expedientes.extend(
                                parse_arrendamiento_block(
                                    texto, fecha_pub, num_boletin, contador + 2, state
                                )
                            )
                        else:
                            texto = ""

                        textos.append(texto)
                        contador += 1

                    except Exception as e_page:
                        log_error_boletin(
                            fecha, l, f"OCR página {contador}", e_page,
                            {"thumb": p.get("thumb"), "contador": contador}
                        )
                        contador += 1
                        continue

            # =============================
            # Rama B) PDF
            # =============================
            else:
                try:
                    direccion = extraer_pdf_source(html=obtener_html(l))
                    if not direccion:
                        raise RuntimeError("No se pudo extraer PDF source (direccion vacía).")
                except Exception as e_pdfsrc:
                    log_error_boletin(fecha, l, "Extraer PDF source", e_pdfsrc)
                    continue

                try:
                    path_salida = descargar_pdf(direccion, f"boletin_{fecha.isoformat()}.pdf")
                    if path_salida is None:
                        # no existe / error de red -> ya se logueó adentro o warning, seguimos
                        continue
                except Exception as e_dl:
                    log_error_boletin(fecha, l, "Descargar PDF", e_dl, {"url_pdf": direccion})
                    continue

                try:
                    texto = extraer_texto_pypdf_con_paginas(path_salida)
                    textos.append(texto)

                    # limpia PDF temporal
                    try:
                        eliminar_pdf(path_salida)
                    except Exception:
                        pass

                    contador = extraer_total_paginas(texto)
                    expedientes.extend(parse_arrendamiento_salas_block_v2(texto, fecha.isoformat(), 38, 2))

                except Exception as e_pdf:
                    log_error_boletin(fecha, l, f"Procesar PDF ({path_salida})", e_pdf)
                    try:
                        eliminar_pdf(path_salida)
                    except Exception:
                        pass
                    continue

            # =============================
            # Guardar revisión incremental (NO debe tronar)
            # =============================
            try:
                if (settings.is_debbug or "").strip().lower() == "true":
                    fecha_string = fecha.isoformat()
                    ruta_salida = f"revision_boletin{fecha_string}.txt"
                    for idx, t in enumerate(textos, start=1):
                        guardar_texto_incremental(ruta_salida, t, idx)
                else:
                    print("Debug desactivado")
            except Exception as e_rev:
                log_error_boletin(fecha, l, "Guardar revisión incremental", e_rev)

            # =============================
            # Insertar en BD (NO debe tronar)
            # =============================
            try:
                # ✅ condición correcta
                if expedientes is not None and len(expedientes) > 0:
                    cantidad_insercion = insertar_expedientes_bulk(expedientes)
                else:
                    cantidad_insercion = 0

                if cantidad_insercion > 0:
                    insertar_procesamiento_boletin(
                        fecha_boletin=fecha,
                        url_boletin=l,
                        estado="TERMINADO",
                        descargado=False,
                        nombre_archivo="",
                        total_paginas=contador,
                        total_expedientes=len(expedientes),
                    )

            except Exception as e_db:
                log_error_boletin(fecha, l, "Inserción BD", e_db, {"total_expedientes": len(expedientes)})
                continue

        except Exception as e_boletin:
            # Catch-all: si algo se nos escapó, log y continuar con el siguiente boletín
            log_error_boletin(fecha, l, "Boletín (catch-all)", e_boletin)
            continue
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Ejecuta una sola vez y termina.")
    parser.add_argument("--interval", type=int, default=0, help="Segundos entre ejecuciones (si no usas --once).")
    args = parser.parse_args()

    if args.once or args.interval <= 0:
        run_once()
    else:
        while True:
            run_once()
            time.sleep(args.interval)
