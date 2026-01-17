
def guardar_texto_incremental(ruta_archivo, texto, pagina):
    with open(ruta_archivo, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write(f"Página {pagina}\n")
        f.write("=" * 80 + "\n")
        f.write(texto.strip() + "\n")


