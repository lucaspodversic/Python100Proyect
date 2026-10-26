"""Generador mínimo de PDFs de texto (sólo para fixtures de tests).

Escribe un PDF válido con fuente Helvetica estándar (no requiere
embebido) y la tabla xref con offsets correctos, sin dependencias.
"""
from __future__ import annotations


def _escapar(t: str) -> str:
    """Escapa los caracteres especiales de los strings literales PDF: \\, ( y )."""
    # La barra primero; si no, se duplicarían las barras agregadas para los paréntesis.
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def crear_pdf(paginas: list[list[tuple[float, float, str]]], tam_fuente: int = 11) -> bytes:
    """`paginas` es una lista de páginas; cada página, una lista de (x, y, texto).

    El texto debe ser latin-1 (WinAnsiEncoding).
    """
    objetos: list[bytes] = []
    n_pag = len(paginas)
    # 1: catálogo, 2: árbol de páginas, 3: fuente, luego (página, contenido) por cada página
    # → la página i es el objeto 4+2i y su contenido el 5+2i.
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pag))
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pag} >>".encode())
    # Helvetica es una de las 14 fuentes estándar: todo lector la tiene, no hay que embeberla.
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, pag in enumerate(paginas):
        # Un bloque BT…ET por texto: fuente, posición absoluta (Td desde el origen) y Tj para dibujar.
        # Coordenadas PDF: origen abajo a la izquierda, carta = 612×792 puntos.
        flujo = "".join(f"BT /F1 {tam_fuente} Tf {x} {y} Td ({_escapar(t)}) Tj ET\n" for x, y, t in pag).encode("latin-1")
        objetos.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                       f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode())
        # /Length debe coincidir exactamente con los bytes del stream.
        objetos.append(b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"endstream")
    salida = bytearray(b"%PDF-1.4\n")
    # La tabla xref necesita el offset en bytes de cada objeto: se anota antes de escribirlo.
    offsets = []
    for num, obj in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida += f"{num} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(salida)
    # Entrada 0 obligatoria (objeto libre, generación 65535); cada línea mide exactamente 20 bytes.
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    salida += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    # trailer: raíz del documento y posición de la xref para que el lector la encuentre desde el final.
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(salida)
