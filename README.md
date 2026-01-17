# boletin-judicial-scraper
Proyecto para la obtención de información relacionada al boletín judicial
# Boletin Judicial Scraper

## Requisitos
- Python 3.11 o 3.12 (recomendado)
- Git
- Acceso y credenciales a PostgreSQL (si aplica)

Nota: La carpeta .venv NO se sube al repositorio. Cada equipo debe crear su propio entorno virtual.

## Clonar repositorio
HTTPS:
```bash
git clone https://github.com/HannDz/boletin-judicial-scraper.git
cd boletin-judicial-scraper
SSH (opcional):

bash
Copy code
git clone git@github.com:HannDz/boletin-judicial-scraper.git
cd boletin-judicial-scraper
Variables de entorno (.env)
Crear el archivo .env a partir del ejemplo:

bash
Copy code
cp .env.example .env
Editar .env y colocar los valores reales. Ejemplo:

env
Copy code
DATABASE_URL=postgresql+psycopg://usuario:password@host:5432/boletin_judicial
Importante: NO subir .env a Git.

Instalación y ejecución (macOS / Linux)
Crear entorno virtual:

bash
Copy code
python3 -m venv .venv
Activar entorno:

bash
Copy code
source .venv/bin/activate
Instalar dependencias:

bash
Copy code
python -m pip install --upgrade pip
pip install -r requirements.txt
Ejecutar:

bash
Copy code
python main.py
Instalación y ejecución (Windows PowerShell)
Crear entorno virtual:

powershell
Copy code
py -m venv .venv
Activar entorno:

powershell
Copy code
.\.venv\Scripts\Activate.ps1
Instalar dependencias:

powershell
Copy code
python -m pip install --upgrade pip
pip install -r requirements.txt
Ejecutar:

powershell
Copy code
python main.py
Si PowerShell bloquea Activate.ps1 (solo una vez):

powershell
Copy code
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
Troubleshooting
Si funciona en Terminal pero falla en Debug de VS Code:

En VS Code: Cmd+Shift+P → Python: Select Interpreter

Seleccionar el intérprete del proyecto:

macOS/Linux: ./venv/bin/python o ./.venv/bin/python

Windows: ..venv\Scripts\python.exe

Opcional: crear .vscode/settings.json con:

json
Copy code
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python"
}
Si sale ModuleNotFoundError (paquetes faltantes):
Con el entorno activado:

bash
Copy code
pip install -r requirements.txt
Verificación rápida (con el entorno activado):

bash
Copy code
python -c "import requests; from dotenv import load_dotenv; import sqlalchemy; import psycopg; print('OK')"
Dependencias mínimas requeridas
requests

python-dotenv

SQLAlchemy

psycopg[binary]