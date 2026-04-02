BoletinScraper (macOS) - Guía de usuario
=======================================

¿Qué hace este programa?
- Consulta/descarga boletines judiciales (según config.env).
- Procesa el contenido (OCR incluido) para extraer información.
- Guarda logs de errores y archivos temporales durante el proceso.

Contenido de esta carpeta
- boletin_scraper        : Ejecutable principal (el que debes correr)
- ocr_worker             : Ejecutable auxiliar de OCR (lo usa el programa)
- config.env             : Configuración EDITABLE del programa
- tesseract/             : Tesseract incluido (NO necesitas instalar nada)
- logs/                  : Logs del proceso (errores, depuración)
- tmp/                   : Temporales (imágenes descargadas/procesadas)
- README_USUARIO.txt     : Esta guía

1) Configuración (config.env)
- Abre el archivo config.env y edita los valores según tu necesidad.
- El programa siempre toma el config.env que está en esta misma carpeta.

2) Cómo ejecutar (manual)
En terminal se debe ejecutar al nivel de carpeta "xattr -dr com.apple.quarantine" para dar permisos, 
Opción A - Finder
- Clic derecho sobre "boletin_scraper" -> Abrir
- Si macOS lo bloquea:
  System Settings -> Privacy & Security -> "Open Anyway / Abrir de todos modos"

Opción B - Terminal (recomendado)
1) Abre Terminal
2) Entra a la carpeta donde está el programa:
   cd /ruta/a/esta/carpeta
3) Ejecuta:
   ./boletin_scraper

3) Logs y errores
- Errores: logs/errores_boletin.log
- Si algo falla, revisa ese archivo primero.

4) Temporales
- La carpeta tmp/ guarda imágenes y archivos temporales.
- Si el programa se interrumpe, puedes borrar el contenido de tmp/ sin problema
  (solo asegúrate de que el programa no esté corriendo).

5) Importante (OCR incluido)
- Esta entrega ya incluye Tesseract en la carpeta tesseract/.
- No borres ni cambies esa carpeta, porque el OCR depende de ella.

6) Si el programa no corre
- Verifica que config.env exista en esta carpeta.
- Ejecuta desde Terminal para ver mensajes:
  ./boletin_scraper
- Revisa logs/errores_boletin.log



BoletinScraper (Windows) - Guía de usuario
=========================================

¿Qué hace este programa?
- Consulta/descarga boletines judiciales (según config.env).
- Procesa el contenido (OCR incluido) para extraer información.
- Guarda logs de errores y temporales.

Contenido de esta carpeta (Windows)
- boletin_scraper.exe     : Ejecutable principal (el que debes correr)
- ocr_worker.exe          : Ejecutable auxiliar de OCR (lo usa el programa)
- config.env              : Configuración EDITABLE del programa
- tesseract\              : Tesseract incluido (NO necesitas instalar nada)
- logs\                   : Logs del proceso
- tmp\                    : Temporales
- README_USUARIO.txt      : Esta guía

1) Configuración
- Abre config.env con Bloc de notas / VS Code y ajusta valores.

2) Ejecutar
- Doble clic en boletin_scraper.exe

3) Logs
- Revisa logs\errores_boletin.log

4) Importante (OCR incluido)
- Esta entrega ya incluye Tesseract en la carpeta tesseract\
- No borres esa carpeta.