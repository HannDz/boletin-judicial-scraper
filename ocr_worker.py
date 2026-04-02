# ocr_worker.py
import sys
import json
import cv2
from pathlib import Path

# IMPORTANTE: reutiliza exactamente el OCR ya probado en images.py
# (no reescribimos nada, solo lo invocamos)
from images import preprocesar_imagen, ocr_imagen, ocr_por_columnas
from configuration import settings


def main(img_path: str) -> str:
    p = Path(img_path)
    if not p.exists():
        raise RuntimeError(f"No existe la imagen: {img_path}")

    img = cv2.imread(str(p))
    if img is None:
        raise RuntimeError(f"No pude leer la imagen: {img_path}")

    # usa el mismo preprocesado ya probado
    img_proc = preprocesar_imagen(str(p), settings.is_debbug)

    # usa el mismo OCR probado: 2 columnas cuando aplique
    # (si tu lógica decide por columnas siempre, usa ocr_por_columnas)
    try:
        texto = ocr_por_columnas(img_proc)
    except Exception:
        # fallback al OCR normal si algo falla
        texto = ocr_imagen(img_proc)

    return texto or ""


if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            raise RuntimeError("Uso: ocr_worker <ruta_imagen.jpg>")

        path = sys.argv[1]
        text = main(path)

        print(json.dumps({"ok": True, "text": text}, ensure_ascii=False))
        sys.exit(0)

    except Exception:
        # JSON siempre, para que el caller lo pueda parsear
        print(json.dumps({"ok": False, "text": ""}, ensure_ascii=False))
        sys.exit(1)