"""Aplicación FastAPI: rutas HTTP, autenticación y wiring de dependencias.

Ejecutar en desarrollo::

    uvicorn app.main:app --reload

``crear_app`` es una fábrica: los tests crean una app aislada con su propia BD
temporal y un reloj fijo (``hoy``) para que las pruebas sean deterministas.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import esquemas, servicio
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Habitacion, Reserva, Rol, Token, Usuario
from .seguridad import hash_token, hashear_password, nuevo_token, verificar_password


def crear_app(
    url_bd: str = "sqlite:///hotel.db",
    admin_email: str = "admin@hotel.local",
    admin_password: str | None = None,
    reloj: Callable[[], date] = date.today,
) -> FastAPI:
    """Construye la aplicación.

    Args:
        url_bd: URL de la base de datos.
        admin_email: email del administrador inicial.
        admin_password: contraseña del admin; si es ``None`` se lee de la
            variable de entorno ``HOTEL_ADMIN_PASSWORD`` (no se crea admin si falta).
        reloj: función que devuelve "hoy"; inyectable para tests.
    """
    app = FastAPI(title="Reservas de hotel", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    fabrica = crear_fabrica_sesiones(motor)
    app.state.fabrica = fabrica
    app.state.reloj = reloj

    # --- Alta del administrador inicial (idempotente) ---
    password = admin_password or os.environ.get("HOTEL_ADMIN_PASSWORD")
    if password:
        with fabrica.begin() as s:
            if s.scalar(select(Usuario).where(Usuario.email == admin_email)) is None:
                s.add(Usuario(email=admin_email, nombre="Administración",
                              password_hash=hashear_password(password), rol=Rol.ADMIN))

    # --- Dependencias ---
    def obtener_sesion() -> Iterator[Session]:
        """Abre una sesión por petición dentro de una transacción.

        Si la ruta lanza una excepción se hace rollback automáticamente.
        """
        with fabrica.begin() as sesion:
            yield sesion

    def usuario_actual(
        authorization: str | None = Header(default=None),
        sesion: Session = Depends(obtener_sesion),
    ) -> Usuario:
        """Resuelve el usuario a partir de ``Authorization: Bearer <token>``."""
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "falta el token Bearer")
        token = sesion.scalar(
            select(Token).where(Token.token_hash == hash_token(authorization[7:]))
        )
        if token is None:
            raise HTTPException(401, "token inválido")
        return token.usuario

    def solo_admin(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        """Restringe la ruta a administradores (403 si no lo es)."""
        if usuario.rol != Rol.ADMIN:
            raise HTTPException(403, "requiere rol administrador")
        return usuario

    # --- Manejo uniforme de errores de negocio ---
    @app.exception_handler(servicio.ErrorNegocio)
    async def _error_negocio(_req: Request, exc: servicio.ErrorNegocio) -> JSONResponse:
        return JSONResponse(status_code=exc.codigo, content={"detail": exc.mensaje})

    # --- Rutas ---
    @app.get("/salud")
    def salud() -> dict[str, str]:
        """Endpoint de salud para monitoreo."""
        return {"estado": "ok"}

    @app.post("/auth/registro", status_code=201)
    def registro(datos: esquemas.RegistroIn, sesion: Session = Depends(obtener_sesion)) -> dict:
        """Registra un cliente (nunca un admin: el rol no se acepta del cliente)."""
        if sesion.scalar(select(Usuario).where(Usuario.email == datos.email.lower())):
            raise HTTPException(409, "el email ya está registrado")
        usuario = Usuario(email=datos.email.lower(), nombre=datos.nombre,
                          password_hash=hashear_password(datos.password))
        sesion.add(usuario)
        sesion.flush()
        return {"id": usuario.id, "email": usuario.email}

    @app.post("/auth/login", response_model=esquemas.TokenOut)
    def login(datos: esquemas.LoginIn, sesion: Session = Depends(obtener_sesion)) -> esquemas.TokenOut:
        """Valida credenciales y emite un token de sesión."""
        usuario = sesion.scalar(select(Usuario).where(Usuario.email == datos.email.lower()))
        # Mismo mensaje para email o contraseña erróneos (no revela qué falló).
        if usuario is None or not verificar_password(datos.password, usuario.password_hash):
            raise HTTPException(401, "credenciales inválidas")
        token = nuevo_token()
        sesion.add(Token(usuario_id=usuario.id, token_hash=hash_token(token)))
        return esquemas.TokenOut(token=token)

    @app.get("/habitaciones", response_model=list[esquemas.HabitacionOut])
    def listar_habitaciones(sesion: Session = Depends(obtener_sesion)) -> list[Habitacion]:
        """Catálogo público de habitaciones activas."""
        return list(sesion.scalars(select(Habitacion).where(Habitacion.activa.is_(True))
                                   .order_by(Habitacion.numero)))

    @app.post("/habitaciones", response_model=esquemas.HabitacionOut, status_code=201)
    def crear_habitacion(datos: esquemas.HabitacionIn, _a: Usuario = Depends(solo_admin),
                         sesion: Session = Depends(obtener_sesion)) -> Habitacion:
        """Alta de habitación (admin). El número debe ser único."""
        hab = Habitacion(**datos.model_dump())
        sesion.add(hab)
        try:
            sesion.flush()
        except IntegrityError:
            raise HTTPException(409, "ya existe una habitación con ese número") from None
        return hab

    @app.get("/disponibilidad", response_model=list[esquemas.HabitacionOut])
    def disponibilidad(entrada: date, salida: date, huespedes: int = 1,
                       sesion: Session = Depends(obtener_sesion)) -> list[Habitacion]:
        """Habitaciones libres para el rango ``[entrada, salida)``."""
        return servicio.habitaciones_disponibles(sesion, entrada, salida, huespedes)

    @app.post("/reservas", response_model=esquemas.ReservaOut, status_code=201)
    def reservar(datos: esquemas.ReservaIn, usuario: Usuario = Depends(usuario_actual),
                 sesion: Session = Depends(obtener_sesion)) -> Reserva:
        """Crea una reserva para el usuario autenticado."""
        return servicio.crear_reserva(sesion, usuario, datos.habitacion_id, datos.entrada,
                                      datos.salida, datos.huespedes, app.state.reloj())

    @app.get("/reservas", response_model=list[esquemas.ReservaOut])
    def mis_reservas(usuario: Usuario = Depends(usuario_actual),
                     sesion: Session = Depends(obtener_sesion)) -> list[Reserva]:
        """El cliente ve las suyas; el admin ve todas."""
        consulta = select(Reserva).order_by(Reserva.entrada)
        if usuario.rol != Rol.ADMIN:
            consulta = consulta.where(Reserva.usuario_id == usuario.id)
        return list(sesion.scalars(consulta))

    @app.post("/reservas/{reserva_id}/cancelar", response_model=esquemas.ReservaOut)
    def cancelar(reserva_id: int, usuario: Usuario = Depends(usuario_actual),
                 sesion: Session = Depends(obtener_sesion)) -> Reserva:
        """Cancela una reserva (libera la habitación para esas fechas)."""
        return servicio.cancelar_reserva(sesion, usuario, reserva_id, app.state.reloj())

    return app


# Instancia por defecto para ``uvicorn app.main:app``.
# Se crea de forma perezosa solo si se ejecuta como servidor (evita crear hotel.db al importar).
def __getattr__(nombre: str):  # pragma: no cover - solo para uvicorn
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(crear_app(), host="127.0.0.1", port=8000)
