# ocr_bridge.py
from pathlib import Path
import sys
import subprocess
import json


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


ROOT = app_dir()
WORKER = ROOT / ("ocr_worker.exe" if sys.platform.startswith("win") else "ocr_worker")


def ocr_with_worker(image_path: str) -> str:
    img_abs = str(Path(image_path).resolve())

    r = subprocess.run(
        [str(WORKER), img_abs],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )

    if r.returncode != 0:
        raise RuntimeError(f"OCR worker falló.\nSTDOUT:\n{r.stdout}\n\nSTDERR:\n{r.stderr}")

    last = None
    for line in reversed(r.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            last = line
            break

    if not last:
        raise ValueError(f"Salida inesperada del worker:\n{r.stdout}")

    data = json.loads(last)
    if not data.get("ok", False):
        raise RuntimeError(f"OCR worker ok=false: {data}")

    return data.get("text", "")