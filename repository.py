from sqlalchemy import text
from datetime import date
from db import engine  

def insertar_expediente(data: dict) -> int:
    sql = text("""
        insert into expedientes (
          id_expediente, juzgado, actor_demandante, demandado, tipo_juicio,
          fecha_publicacion, extracto_acuerdo, estatus_riesgo,
          numero_boletin, numero_pagina, estatus
        )
        values (
          :id_expediente, :juzgado, :actor_demandante, :demandado, :tipo_juicio,
          :fecha_publicacion, :extracto_acuerdo, :estatus_riesgo,
          :numero_boletin, :numero_pagina, :estatus
        )
        returning id;
    """)

    with engine.begin() as conn:  
        new_id = conn.execute(sql, data).scalar_one()
        return new_id

from datetime import date
from sqlalchemy import text
from db import engine

def insertar_procesamiento_boletin(
    fecha_boletin: date,
    url_boletin: str,
    estado: str = "INICIADO",
    total_paginas: int | None = None,
    total_expedientes: int | None = None,
    descargado: bool | None = None,
    nombre_archivo: str | None = None,
) -> None:
    sql = text("""
        insert into procesamiento_boletin (
            fecha_boletin, url_boletin, estado,
            total_paginas, total_expedientes,
            descargado, nombre_archivo
        ) values (
            :fecha_boletin, :url_boletin, :estado,
            :total_paginas, :total_expedientes,
            :descargado, :nombre_archivo
        );
    """)

    with engine.begin() as conn:
        conn.execute(sql, {
            "fecha_boletin": fecha_boletin,
            "url_boletin": url_boletin,
            "estado": estado,
            "total_paginas": total_paginas,
            "total_expedientes": total_expedientes,
            "descargado": descargado,
            "nombre_archivo": nombre_archivo,
        })

def actualizar_total_paginas(id_procesamiento: int, total_paginas: int) -> None:
    sql = text("""
        update procesamiento_boletin
        set total_paginas = :total_paginas
        where id = :id;
    """)
    with engine.begin() as conn:
        conn.execute(sql, {"id": id_procesamiento, "total_paginas": total_paginas})

def existe_procesamiento(fecha_boletin: date, url_boletin: str) -> bool:
    sql = text("""
        select 1
        from procesamiento_boletin
        where fecha_boletin = :fecha
          and url_boletin = :url
        limit 1;
    """)
    with engine.connect() as conn:
        return conn.execute(sql, {"fecha": fecha_boletin, "url": url_boletin}).first() is not None

SQL_INSERT_EXPEDIENTES = text("""
insert into expedientes (
  id_expediente, actor_demandante, demandado, tipo_juicio,
  fecha_publicacion,
  numero_boletin, numero_pagina, estatus
) values (
  :id_expediente, :actor_demandante, :demandado, :tipo_juicio,
  :fecha_publicacion,
  :numero_boletin, :numero_pagina, :estatus
);
""")

CAMPOS_EXPEDIENTE = [
    "id_expediente",
    "juzgado",
    "actor_demandante",
    "demandado",
    "tipo_juicio",
    "fecha_publicacion",
    "extracto_acuerdo",
    "estatus_riesgo",
    "numero_boletin",
    "numero_pagina",
    "estatus",
]

def normalizar_registro(reg: dict) -> dict:
    # crea un dict con todas las llaves esperadas
    return {k: reg.get(k) for k in CAMPOS_EXPEDIENTE}

# def insertar_expedientes_bulk(registros: list[dict], batch_size: int = 1000):
#     registros_norm = [normalizar_registro(r) for r in registros]

#     with engine.begin() as conn:
#         for i in range(0, len(registros_norm), batch_size):
#             conn.execute(SQL_INSERT_EXPEDIENTES, registros_norm[i:i+batch_size])

def insertar_expedientes_bulk(registros: list[dict], batch_size: int = 1000) -> int:
    registros_norm = [normalizar_registro(r) for r in registros]
    total_insertadas = 0

    with engine.begin() as conn:
        for i in range(0, len(registros_norm), batch_size):
            batch = registros_norm[i:i + batch_size]
            result = conn.execute(SQL_INSERT_EXPEDIENTES, batch)
            total_insertadas += result.rowcount if result.rowcount is not None else len(batch)

    return total_insertadas



