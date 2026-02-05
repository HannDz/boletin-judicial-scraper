import cv2
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'/opt/homebrew/bin/tesseract'
import numpy as np
import os
import time
import random
import requests
import json
from datetime import datetime
from configuration import settings

def log_error_imagen(path_txt: str, url: str, path_img: str, err: str):
    os.makedirs(os.path.dirname(path_txt) or ".", exist_ok=True)
    with open(path_txt, "a", encoding="utf-8") as f:
        f.write(f"URL: {url}\nPATH: {path_img}\nERROR: {err}\n{'-'*80}\n")

def descargar_imagen(session, url_img, path, intentos=3, timeout=(10, 60), log_path="errores_imagenes.txt"):
    last_err = None

    for intento in range(1, intentos + 1):
        try:
            r = session.get(url_img, timeout=timeout)
            r.raise_for_status()

            # escribe binario
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "wb") as f:
                f.write(r.content)

            # ✅ valida que exista y tenga contenido
            if not os.path.exists(path) or os.path.getsize(path) < 200:  # 200 bytes ~ mínimo razonable
                raise IOError(f"Archivo descargado vacío o muy pequeño ({os.path.getsize(path) if os.path.exists(path) else 'no existe'} bytes)")

            return True

        except Exception as e:
            last_err = f"Intento {intento}/{intentos} => {repr(e)}"
            # espera incremental
            time.sleep(1.5 * intento)

    # si falló todo, log
    log_error_imagen(log_path, url_img, path, last_err or "Error desconocido")
    return False

def procesar_pagina(session, url_img, idx):
    path = f"tmp/pagina_{idx}.jpg"

    descargar_imagen(session, url_img, path)
    img = preprocesar_imagen(path, settings.is_debbug)
    texto = ocr_imagen(img)

    try:
        os.remove(path)
    except FileNotFoundError:
        pass

    return texto

def ocr_imagen(img):
    return pytesseract.image_to_string(
        img,
        lang="spa+eng",
        config="--psm 4 --oem 3"
    )

def preprocesar_base(path):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    img = cv2.medianBlur(img, 3)
    img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return img

def mejorar_resolucion(img):
    return cv2.resize(
        img,
        None,
        fx=1.5,
        fy=1.5,
        interpolation=cv2.INTER_CUBIC
    )

def unir_letras(img):
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    return cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)

def limpiar_ruido(img):
    return cv2.medianBlur(img, 3)

def preprocesar_imagen(path, debug=settings.is_debbug):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

    img = cv2.resize(
        img,
        None,
        fx=1.7,
        fy=1.7,
        interpolation=cv2.INTER_CUBIC
    )

    img = cv2.medianBlur(img, 3)

    img = cv2.threshold(
        img, 0, 255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )[1]

    # if debug:
    #     cv2.imwrite(
    #         f"tmp/debug_{os.path.basename(path)}",
    #         img
    #     )

    return img

def ocr_por_columnas(img):
    h, w = img.shape[:2]
    mitad = w // 2

    col_izq = img[:, :mitad]
    col_der = img[:, mitad:]

    texto_izq = ocr_imagen(col_izq)
    texto_der = ocr_imagen(col_der)

    return texto_izq + "\n" + texto_der

def procesar_pagina_columna(session, url_img, idx):
    path = f"tmp/pagina_{idx}.jpg"
    #path = f"tmp/boletin_prueba.jpg"
    descargar_imagen(session, url_img, path)
    img = preprocesar_imagen_columna(path, settings.is_debbug)
    if img is None:
    # ya quedó logueado, continúas flujo
        return ""
    #img = cv2.imread()
    texto = ocr_por_columnas(img)

    try:
        os.remove(path)
    except FileNotFoundError:
        pass

    return texto

def preprocesar_imagen_columna(path, debug=True, log_path="errores_imagenes.txt"):
    # 1) Validaciones básicas
    if not path or not os.path.exists(path):
        log_error_imagen(log_path, url="(sin url)", path_img=path, err="Archivo no existe")
        return None

    if os.path.getsize(path) < 200:
        log_error_imagen(log_path, url="(sin url)", path_img=path, err=f"Archivo muy pequeño ({os.path.getsize(path)} bytes)")
        return None

    # 2) Leer imagen
    img = cv2.imread(path)
    if img is None or img.size == 0:
        log_error_imagen(log_path, url="(sin url)", path_img=path, err="cv2.imread devolvió None (archivo corrupto/no imagen)")
        return None

    # 3) (Opcional) Generar versión procesada SOLO para debug
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 40))
        mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        resultado = cv2.inpaint(img, mask, 7, cv2.INPAINT_TELEA)

        if settings.is_debbug:
            os.makedirs("tmp", exist_ok=True)
            # guarda original y procesada para comparar
            cv2.imwrite(f"tmp/orig_{os.path.basename(path)}", img)
            cv2.imwrite(f"tmp/proc_{os.path.basename(path)}", resultado)

    except Exception as e:
        # si falla el preproceso, NO rompas flujo: solo log y sigues con original
        log_error_imagen(log_path, url="(sin url)", path_img=path, err=f"Preproceso falló pero se usa original: {repr(e)}")

    # ✅ 4) Retorna ORIGINAL porque es el que dices que OCR lee mejor
    return img

def eliminar_solo_consulta(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Umbral moderado
    _, thresh = cv2.threshold(
        gray, 0, 255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    # Encontrar contornos
    contornos, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # Máscara VACÍA
    mask = np.zeros(gray.shape, dtype=np.uint8)

    # Filtrar solo objetos grandes
    for c in contornos:
        area = cv2.contourArea(c)
        if area > 5000:   # ← CLAVE
            cv2.drawContours(mask, [c], -1, 255, -1)

    # Engrosar un poco SOLO lo grande
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    mask = cv2.dilate(mask, kernel, iterations=1)

    # Inpainting
    limpio = cv2.inpaint(img, mask, 7, cv2.INPAINT_TELEA)
    return limpio

def reprocesar_fallos_descarga(session, log_path="fallos_descarga.jsonl"):
    fallos = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fallos.append(json.loads(line))

    # dedupe por URL (toma el último)
    ult = {}
    for x in fallos:
        if x.get("fase") == "download":
            ult[x["url"]] = x

    pendientes = list(ult.values())
    ok_count = 0
    fail_count = 0

    for item in pendientes:
        ok, err = descargar_imagen(
            session=session,
            url=item["url"],
            path=item["path"],
            page_num=item.get("page"),
            log_path=log_path,
            intentos=6
        )
        if ok:
            ok_count += 1
        else:
            fail_count += 1

    return ok_count, fail_count
