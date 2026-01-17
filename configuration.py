import os
from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path

# Busca .env relativo a ESTE archivo (configuration.py), no al cwd

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / "config.env"

if not ENV_PATH.exists():
    raise FileNotFoundError(f"No existe el archivo .env en: {ENV_PATH}")

load_dotenv(dotenv_path=ENV_PATH)
# Carga .env automáticamente (si existe)
#load_dotenv()

def get_env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    val = os.getenv(key, default)
    if required and (val is None or val == ""):
        raise ValueError(f"Falta variable requerida: {key}")
    return val

def get_int(key: str, default: int | None = None, *, required: bool = False) -> int | None:
    val = get_env(key, None, required=required)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except ValueError as e:
        raise ValueError(f"Variable {key} debe ser entero. Valor actual: {val}") from e

@dataclass(frozen=True)
class Settings:
    # DB
    db_backend: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    # Extras genéricos (ejemplos)
    app_env: str
    log_level: str
    url_boletin:str
    url_boletin_filtro:str
    fecha_ini:str
    fecha_fin:str
    is_debbug:bool

def load_settings() -> Settings:
    return Settings(
        db_backend=(get_env("DB_BACKEND", "postgres") or "postgres").lower(),
        db_host=get_env("DB_HOST", "localhost") or "localhost",
        db_port=get_int("DB_PORT", 5432) or 5432,
        db_name=get_env("DB_NAME", required=True) or "",
        db_user=get_env("DB_USER", required=True) or "",
        db_password=get_env("DB_PASSWORD", required=True) or "",
        #Ejemplo de obtencion de llaves
        url_boletin=get_env("URL_BOLETIN", "") or "",
        app_env=get_env("APP_ENV", "dev") or "dev",
        log_level=get_env("LOG_LEVEL", "INFO") or "INFO",
        url_boletin_filtro=get_env("URL_BOLETIN_FILTRO", "") or "",
        fecha_ini=get_env("FILTRADO_INI","") or "",
        fecha_fin=get_env("FILTRADO_FIN","") or "",
        is_debbug=get_env("ISDEBBUG",False) or False,
    )

settings = load_settings()
