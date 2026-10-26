"""Flujo editorial, revisiones y bloqueo optimista."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from .contenido import slug_unico, slugificar
from .modelos import Articulo, Estado, Revision, Rol, Usuario


class ErrorNegocio(Exception):
    """Violación de una regla de negocio (``codigo`` = estado HTTP)."""
    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        """``mensaje`` va al cliente como 'detail' y ``codigo`` es el estado HTTP (400 por
        defecto; 404, 409, etc. según el caso).
        """
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def es_staff(u: Usuario) -> bool:
    """Editores y admins: pueden ver y editar cualquier artículo y publicar."""
    return u.rol in (Rol.EDITOR, Rol.ADMIN)


def _existe_slug(s: Session, excluir_id: int | None = None):
    """Devuelve una función que dice si un slug ya está usado (sin contar el artículo
    ``excluir_id``), para pasársela a slug_unico.
    """
    def existe(slug: str) -> bool:
        """True si otro artículo ya tiene ese slug."""
        q = select(Articulo.id).where(Articulo.slug == slug)
        if excluir_id is not None:
            q = q.where(Articulo.id != excluir_id)
        return s.scalar(q) is not None
    return existe


def _revision(s: Session, a: Articulo, autor: Usuario, ahora: datetime) -> None:
    """Guarda una foto del artículo con el número de su versión actual."""
    s.add(Revision(articulo_id=a.id, numero=a.version, titulo=a.titulo, cuerpo=a.cuerpo,
                   autor_id=autor.id, fecha=ahora))


def crear(s: Session, autor: Usuario, titulo: str, cuerpo: str, etiquetas: list[str], ahora: datetime) -> Articulo:
    """Crea el borrador con slug único y etiquetas normalizadas (minúsculas, sin vacías ni
    repetidas, ordenadas) y registra la revisión 1.
    """
    a = Articulo(slug=slug_unico(slugificar(titulo), _existe_slug(s)), titulo=titulo, cuerpo=cuerpo,
                 etiquetas=",".join(sorted({e.strip().lower() for e in etiquetas if e.strip()})),
                 autor_id=autor.id)
    s.add(a)
    s.flush()
    _revision(s, a, autor, ahora)
    return a


def obtener_editable(s: Session, aid: int, u: Usuario) -> Articulo:
    """Autores: solo sus artículos. Editores/admin: todos."""
    a = s.get(Articulo, aid)
    if a is None or (not es_staff(u) and a.autor_id != u.id):
        raise ErrorNegocio("artículo inexistente", 404)
    return a


def editar(s: Session, a: Articulo, u: Usuario, version: int, titulo: str, cuerpo: str,
           ahora: datetime) -> Articulo:
    """Edita con **bloqueo optimista**.

    El cliente envía la ``version`` que leyó. El ``UPDATE ... WHERE version = ?``
    solo afecta la fila si nadie la modificó entretanto; si no, 409 y el cliente
    debe recargar y reaplicar sus cambios (no se pisan ediciones ajenas).
    """
    if not es_staff(u) and a.estado not in (Estado.BORRADOR,):
        raise ErrorNegocio("solo podés editar tus borradores", 403)
    r = s.execute(update(Articulo).where(Articulo.id == a.id, Articulo.version == version)
                  .values(titulo=titulo, cuerpo=cuerpo, version=Articulo.version + 1)
                  .execution_options(synchronize_session=False))
    if r.rowcount != 1:
        raise ErrorNegocio("conflicto de edición: el artículo cambió, recargalo", 409)
    s.refresh(a)
    _revision(s, a, u, ahora)
    return a


TRANSICIONES = {
    # (estado actual, acción) → (nuevo estado, ¿requiere staff?)
    (Estado.BORRADOR, "enviar"): (Estado.EN_REVISION, False),
    (Estado.EN_REVISION, "rechazar"): (Estado.BORRADOR, True),
    (Estado.EN_REVISION, "publicar"): (Estado.PUBLICADO, True),
    (Estado.PUBLICADO, "archivar"): (Estado.ARCHIVADO, True),
    (Estado.ARCHIVADO, "restaurar"): (Estado.BORRADOR, True),
}


def accion(a: Articulo, u: Usuario, nombre: str, publicar_en: datetime | None = None) -> Articulo:
    """Aplica una acción del flujo editorial."""
    destino = TRANSICIONES.get((a.estado, nombre))
    if destino is None:
        raise ErrorNegocio(f"acción '{nombre}' no válida en estado {a.estado.value}", 409)
    nuevo, requiere_staff = destino
    if requiere_staff and not es_staff(u):
        raise ErrorNegocio("solo un editor puede hacer esto", 403)
    a.estado = nuevo
    if nombre == "publicar":
        a.publicar_en = publicar_en  # None = inmediato
    return a


def restaurar_revision(s: Session, a: Articulo, u: Usuario, numero: int, ahora: datetime) -> Articulo:
    """Crea una nueva versión con el contenido de una revisión anterior."""
    rev = next((r for r in a.revisiones if r.numero == numero), None)
    if rev is None:
        raise ErrorNegocio("revisión inexistente", 404)
    return editar(s, a, u, a.version, rev.titulo, rev.cuerpo, ahora)


def consulta_publicados(ahora: datetime):
    """Artículos visibles al público: publicados y cuya fecha programada ya pasó."""
    return select(Articulo).where(Articulo.estado == Estado.PUBLICADO,
                                  or_(Articulo.publicar_en.is_(None), Articulo.publicar_en <= ahora))
