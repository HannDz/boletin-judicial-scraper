# main.py
import requests
import os
from scraper import *
from redirection import *
from extractor_js import *
from scraper import *
from images import *
from configuration import settings
from repository import *
from text_extractor import *
os.makedirs("tmp", exist_ok=True)

session = crear_sesion()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

URL_Boletin = settings.url_boletin
textos = []
debug = True
html = obtener_html(URL_Boletin)
html2 = obtener_html_filtrado(settings.url_boletin_filtro,URL_Boletin, settings.fecha_ini, settings.fecha_fin)

externos = extraer_externos(html2,True)
print("HTML obtenido correctamente")

#links = obtener_fechas_y_links_boletines(html, True)

for fecha,l in externos:
    if not existe_procesamiento(fecha, l):
        expedientes=[]
        direccion = extraer_url_redireccion(html = obtener_html(l))
        html = requests.get(direccion).text
        resultado = extraer_paginas_js(html)
        contador = 1
        fecha_pub: date | None = None 
        num_boletin: int
        for p in resultado:
            html_thumb = session.get(p["thumb"]).text 
            print(f"OCR página {html_thumb}")
            if contador == 1 or contador < inicio_columnas:
                texto = procesar_pagina(session, html_thumb, contador)
            else:
                texto = procesar_pagina_columna(session, html_thumb, contador)
                expedientes.extend(parse_arrendamiento_block(texto, fecha_pub, num_boletin, contador+2))
            if contador == 1:
                inicio_columnas = obtener_inicio_columnas(texto)
                fecha_pub , num_boletin = extraer_fecha_y_numero_boletin(texto)

            textos.append(texto)
            if debug:
                if contador == 15:
                    break
            contador+=1
        cantidad_insercion = insertar_expedientes_bulk(expedientes)

        cont = 1
        fecha_string = fecha.isoformat()

        if debug:
            for cont, texto in enumerate(textos, start=1):
                ruta_salida = f"revision_boletin{fecha_string}.txt"
                guardar_texto_incremental(
                    ruta_salida,
                    texto,   
                    cont     
                )
                cont +=1

        if cantidad_insercion > 0:
            insertar_procesamiento_boletin(
            fecha_boletin=fecha,
            url_boletin=l,
            estado="TERMINADO",
            descargado=False,
            nombre_archivo="",#f"boletin_{fecha_string}.pdf",
            total_paginas=contador,
            total_expedientes=len(expedientes),
            )
    else:
        print(f"Ya existe {l}")
   
