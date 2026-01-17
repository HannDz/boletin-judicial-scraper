import cv2
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'/opt/homebrew/bin/tesseract'
import numpy as np
import os
def descargar_imagen(session, url, ruta_salida):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    with open(ruta_salida, "wb") as f:
        f.write(r.content)

def procesar_pagina(session, url_img, idx):
    path = f"tmp/pagina_{idx}.jpg"

    descargar_imagen(session, url_img, path)
    img = preprocesar_imagen(path, True)
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

def preprocesar_imagen(path, debug=False):
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

    if debug:
        cv2.imwrite(
            f"tmp/debug_{os.path.basename(path)}",
            img
        )

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
    img = preprocesar_imagen_columna(path, True)
    #img = cv2.imread()
    texto = ocr_por_columnas(img)

    try:
        os.remove(path)
    except FileNotFoundError:
        pass

    return texto

def     preprocesar_imagen_columna(path, debug=True):
   
# Cargar imagen
    img = cv2.imread(path)
    ## prueba tratando de quitar solo consults. img =  eliminar_solo_consulta(img)
    #Escala de grises
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Umbral para detectar texto negro grande
    _, thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    # Quitar ruido pequeño (dejamos solo letras grandes)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 40))
    mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    # Inpainting (rellenar con fondo)
    resultado = cv2.inpaint(img, mask, 7, cv2.INPAINT_TELEA)

    # Guardar resultado
    cv2.imwrite("boletin_sin_solo_consulta.jpg", resultado)

    if debug:
        os.makedirs("tmp", exist_ok=True)
        cv2.imwrite(f"tmp/debug_{os.path.basename(path)}", img)
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

