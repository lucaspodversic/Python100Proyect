"""API del CMS: zona de redacción (autenticada) y API pública de lectura."""
from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import contenido, servicio
from .auth import crear_auth, crear_usuario
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Articulo, Medio, Rol, Token, Usuario
from .servicio import ErrorNegocio


class ArticuloIn(BaseModel):
    """Alta de artículo: título, cuerpo en Markdown y hasta 15 etiquetas (se normalizan a
    minúsculas y sin repetir).
    """
    titulo: str = Field(min_length=3, max_length=200)
    cuerpo: str = Field(min_length=1, max_length=200_000)
    etiquetas: list[str] = Field(default_factory=list, max_length=15)


class EdicionIn(BaseModel):
    """Edición con bloqueo optimista: ``version`` es la que el cliente leyó; si no coincide con
    la actual, 409.
    """
    version: int
    titulo: str = Field(min_length=3, max_length=200)
    cuerpo: str = Field(min_length=1, max_length=200_000)


class AccionIn(BaseModel):
    """Acción del flujo editorial (enviar, rechazar, publicar, archivar…). ``publicar_en``
    programa la publicación para una fecha futura.
    """
    accion: str
    publicar_en: datetime | None = None


class RolIn(BaseModel):
    """Cambio de rol (solo admin)."""
    rol: Rol


def ahora_utc() -> datetime:
    """Hora actual en UTC sin zona, como la guarda SQLite. Se inyecta como ``reloj`` para que
    los tests controlen la publicación programada.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _privado(a: Articulo) -> dict:
    """Vista completa de un artículo para su autor o el staff (incluye estado, versión y
    Markdown crudo). La vista pública solo expone slug, título y HTML saneado.
    """
    return {"id": a.id, "slug": a.slug, "titulo": a.titulo, "cuerpo": a.cuerpo, "estado": a.estado.value,
            "version": a.version, "autor_id": a.autor_id, "etiquetas": [e for e in a.etiquetas.split(",") if e],
            "publicar_en": a.publicar_en.isoformat() if a.publicar_en else None}


def crear_app(url_bd: str = "sqlite:///cms.db", dir_medios: str | Path = "medios",
              admin_email: str = "admin@cms.local", admin_password: str | None = None,
              reloj: Callable[[], datetime] = ahora_utc) -> FastAPI:
    """Arma la API del CMS: tablas, carpeta de medios, admin semilla (sin contraseña por
    defecto), autenticación y rutas de artículos, medios y lectura pública.
    """
    app = FastAPI(title="CMS", version="1.0.0")
    medios = Path(dir_medios)
    medios.mkdir(parents=True, exist_ok=True)
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    fabrica = app.state.fabrica = crear_fabrica_sesiones(motor)
    password = admin_password or os.environ.get("CMS_ADMIN_PASSWORD")
    if password:
        with fabrica.begin() as s:
            if s.scalar(select(Usuario).where(Usuario.email == admin_email)) is None:
                crear_usuario(s, Usuario, admin_email, "Admin", password, Rol.ADMIN)
    auth = crear_auth(fabrica, Usuario, Token, Rol.AUTOR)
    app.include_router(auth.router)
    S = Depends(auth.obtener_sesion)
    yo = Depends(auth.usuario_actual)
    admin = Depends(auth.requiere_rol(Rol.ADMIN))
    staff = Depends(auth.requiere_rol(Rol.EDITOR, Rol.ADMIN))

    @app.exception_handler(ErrorNegocio)
    async def _err(_r: Request, e: ErrorNegocio) -> JSONResponse:
        """Traduce ErrorNegocio a una respuesta JSON con su código y {'detail': mensaje}, el
        mismo formato que usan las HTTPException de FastAPI.
        """
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    @app.patch("/usuarios/{uid}/rol", dependencies=[admin])
    def rol(uid: int, d: RolIn, s: Session = S) -> dict:
        """Admin: cambia el rol de un usuario (autor, editor o admin)."""
        u = s.get(Usuario, uid)
        if u is None:
            raise HTTPException(404, "usuario inexistente")
        u.rol = d.rol
        return {"id": uid, "rol": d.rol.value}

    # ------------------------------------------------------------ redacción
    @app.post("/articulos", status_code=201)
    def crear(d: ArticuloIn, u: Usuario = yo, s: Session = S) -> dict:
        """Cualquier usuario crea un borrador propio; el slug se genera del título y se
        desambigua.
        """
        return _privado(servicio.crear(s, u, d.titulo, d.cuerpo, d.etiquetas, reloj()))

    @app.get("/articulos")
    def listar(u: Usuario = yo, s: Session = S) -> list[dict]:
        """Autor: sus artículos. Staff: todos."""
        q = select(Articulo).order_by(Articulo.id)
        if not servicio.es_staff(u):
            q = q.where(Articulo.autor_id == u.id)
        return [_privado(a) for a in s.scalars(q)]

    @app.put("/articulos/{aid}")
    def editar(aid: int, d: EdicionIn, u: Usuario = yo, s: Session = S) -> dict:
        """Edita título y cuerpo con bloqueo optimista; cada edición crea una revisión nueva."""
        a = servicio.obtener_editable(s, aid, u)
        return _privado(servicio.editar(s, a, u, d.version, d.titulo, d.cuerpo, reloj()))

    @app.post("/articulos/{aid}/flujo")
    def flujo(aid: int, d: AccionIn, u: Usuario = yo, s: Session = S) -> dict:
        """Aplica una acción del flujo editorial validando estado y rol (ver
        servicio.TRANSICIONES).
        """
        a = servicio.obtener_editable(s, aid, u)
        cuando = d.publicar_en.astimezone(timezone.utc).replace(tzinfo=None) if d.publicar_en and d.publicar_en.tzinfo else d.publicar_en
        return _privado(servicio.accion(a, u, d.accion, cuando))

    @app.get("/articulos/{aid}/revisiones")
    def revisiones(aid: int, u: Usuario = yo, s: Session = S) -> list[dict]:
        """Historial de revisiones del artículo, de la más vieja a la más nueva."""
        a = servicio.obtener_editable(s, aid, u)
        return [{"numero": r.numero, "titulo": r.titulo, "autor_id": r.autor_id, "fecha": r.fecha.isoformat()}
                for r in a.revisiones]

    @app.post("/articulos/{aid}/revisiones/{numero}/restaurar")
    def restaurar(aid: int, numero: int, u: Usuario = yo, s: Session = S) -> dict:
        """Restaura el contenido de una revisión anterior. No reescribe la historia: crea una
        versión NUEVA con ese contenido.
        """
        a = servicio.obtener_editable(s, aid, u)
        return _privado(servicio.restaurar_revision(s, a, u, numero, reloj()))

    @app.delete("/articulos/{aid}", status_code=204, dependencies=[staff])
    def borrar(aid: int, u: Usuario = yo, s: Session = S) -> None:
        """Staff: borra un artículo con sus revisiones."""
        s.delete(servicio.obtener_editable(s, aid, u))

    # ------------------------------------------------------------ medios
    @app.post("/medios", status_code=201)
    async def subir(archivo: UploadFile = File(...), u: Usuario = yo, s: Session = S) -> dict:
        """Sube una imagen validando tamaño y **contenido real** (números mágicos)."""
        datos = await archivo.read(contenido.MAX_IMAGEN + 1)
        if len(datos) > contenido.MAX_IMAGEN:
            raise HTTPException(413, "la imagen supera 2 MiB")
        detectado = contenido.detectar_imagen(datos)
        if detectado is None:
            raise HTTPException(415, "solo se aceptan PNG, JPEG o GIF")
        mime, ext = detectado
        nombre = f"{secrets.token_hex(16)}.{ext}"  # nombre aleatorio: sin path traversal
        (medios / nombre).write_bytes(datos)
        m = Medio(archivo=nombre, nombre_original=(archivo.filename or "")[:200], tipo=mime,
                  bytes=len(datos), subido_por=u.id)
        s.add(m)
        s.flush()
        return {"id": m.id, "url": f"/medios/{nombre}", "tipo": mime}

    @app.get("/medios/{nombre}")
    def servir(nombre: str, s: Session = S) -> FileResponse:
        """Sirve solo archivos registrados en la base (un nombre arbitrario o con '..' da 404).
        Agrega 'nosniff' para que el navegador no reinterprete el tipo.
        """
        m = s.scalar(select(Medio).where(Medio.archivo == nombre))  # solo nombres registrados
        if m is None:
            raise HTTPException(404, "medio inexistente")
        return FileResponse(medios / m.archivo, media_type=m.tipo,
                            headers={"X-Content-Type-Options": "nosniff"})

    # ------------------------------------------------------------ pública
    @app.get("/publico/articulos")
    def publicos(etiqueta: str | None = None, s: Session = S) -> list[dict]:
        """Lectura pública: publicados cuya fecha de publicación ya llegó, del más nuevo al más
        viejo, filtrables por etiqueta.
        """
        q = servicio.consulta_publicados(reloj()).order_by(Articulo.id.desc())
        res = [a for a in s.scalars(q) if not etiqueta or etiqueta.lower() in a.etiquetas.split(",")]
        return [{"slug": a.slug, "titulo": a.titulo} for a in res]

    @app.get("/publico/articulos/{slug}")
    def publico(slug: str, s: Session = S) -> dict:
        """Un artículo público por slug, con el Markdown convertido a HTML saneado."""
        a = s.scalar(servicio.consulta_publicados(reloj()).where(Articulo.slug == slug))
        if a is None:
            raise HTTPException(404, "artículo inexistente")
        return {"slug": a.slug, "titulo": a.titulo, "html": contenido.renderizar(a.cuerpo)}

    return app


def __getattr__(nombre: str):  # pragma: no cover
    """Atributo perezoso del módulo: ``uvicorn app.main:app`` pide ``app`` y recién ahí se
    crea, así importar el módulo (por ejemplo en los tests) no abre ninguna base.
    """
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
