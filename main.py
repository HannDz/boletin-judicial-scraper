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
from text_pdf_extractor import *
os.makedirs("tmp", exist_ok=True)

session = crear_sesion()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

URL_Boletin = settings.url_boletin
textos = []
debug = settings.is_debbug
#html = obtener_html(URL_Boletin)
html2 = obtener_html_filtrado(settings.url_boletin_filtro,URL_Boletin, settings.fecha_ini, settings.fecha_fin)

externos = extraer_externos(html2,settings.is_debbug)
print("HTML obtenido correctamente")

#links = obtener_fechas_y_links_boletines(html, settings.is_debbug)

for fecha,l in externos:
    if not existe_procesamiento(fecha, l):
        expedientes=[]
        direccion = extraer_url_redireccion(html = obtener_html(l))
        contador = 0
        if direccion != None:
            html = requests.get(direccion).text
            resultado = extraer_paginas_js(html)
            contador = 1
            fecha_pub: date | None = None 
            num_boletin: int
            for p in resultado:
                html_thumb = session.get(p["thumb"]).text 
                print(f"OCR página {html_thumb}")
                if contador == 1:
                    texto = procesar_pagina(session, html_thumb, contador)
                    inicio_columnas = obtener_inicio_columnas(texto)
                    fecha_pub , num_boletin = extraer_fecha_y_numero_boletin(texto)
                elif inicio_columnas <= contador:
                    texto = procesar_pagina_columna(session, html_thumb, contador)
                    expedientes.extend(parse_arrendamiento_block(texto, fecha_pub, num_boletin, contador+2))

                if debug:
                    textos.append(texto)
                    if contador == inicio_columnas+15:
                        break
                contador+=1
        else:
            direccion = extraer_pdf_source(html = obtener_html(l))
            path_salida = descargar_pdf(direccion, f"boletin_{fecha.isoformat()}.pdf")
            texto = extraer_texto_pypdf_con_paginas(path_salida)
            eliminar_pdf(path_salida) 
            contador = extraer_total_paginas(texto)
            texto_limpio = limpiar_ruido_boletin(texto)
            expedientes.extend(parse_arrendamiento_salas_block_v2(texto_limpio, fecha.isoformat(), 38, 2))
        
        cont = 1
        fecha_string = fecha.isoformat()
        if debug:
            textos.append(texto)
            for cont, texto in enumerate(textos, start=1):
                ruta_salida = f"revision_boletin{fecha_string}.txt"
                guardar_texto_incremental(
                    ruta_salida,
                    texto,   
                    cont     
                )
                cont +=1
        
        if expedientes != None or len(expedientes) > 0:
            cantidad_insercion = insertar_expedientes_bulk(expedientes)

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
   
