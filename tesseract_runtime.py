import os
import sys
from pathlib import Path

def _app_dir() -> Path:
    # cuando está empaquetado con PyInstaller
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # cuando corre como scripts
    return Path(__file__).resolve().parent

def configure_tesseract_if_bundled() -> None:
    """
    Si existe ./tesseract/ junto al ejecutable, configura pytesseract para usarlo
    y setea TESSDATA_PREFIX a ./tesseract/tessdata.
    """
    base = _app_dir()
    tess_dir = base / "tesseract"

    win_exe = tess_dir / "tesseract.exe"
    mac_bin = tess_dir / "tesseract"

    if win_exe.exists():
        tess_cmd = win_exe
    elif mac_bin.exists():
        tess_cmd = mac_bin
    else:
        # no hay tesseract embebido (puede estar instalado en sistema)
        return

    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = str(tess_cmd)

    tessdata = tess_dir / "tessdata"
    if tessdata.exists():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)