"""Autenticación y autorización reutilizable (registro, login, roles).

Se construye con ``crear_auth`` pasando la fábrica de sesiones y los modelos
``Usuario`` y ``Token`` del proyecto. Devuelve:

- ``obtener_sesion``: dependencia FastAPI que abre una transacción por petición
  (commit al terminar, rollback si hay excepción).
- ``usuario_actual``: resuelve el usuario desde ``Authorization: Bearer <token>``.
- ``requiere_rol(*roles)``: fábrica de dependencias que exige uno de los roles.
- ``router``: rutas ``POST /auth/registro`` y ``POST /auth/login``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .seguridad import hash_token, hashear_password, nuevo_token, verificar_password


class RegistroIn(BaseModel):
    """Datos de alta de un usuario (siempre con el rol por defecto)."""

    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    nombre: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    """Credenciales de inicio de sesión."""

    email: str
    password: str


@dataclass
class Auth:
    """Agrupa las dependencias de autenticación generadas por ``crear_auth``."""

    obtener_sesion: Callable[..., Iterator[Session]]
    usuario_actual: Callable[..., Any]
    requiere_rol: Callable[..., Callable[..., Any]]
    router: APIRouter


def crear_auth(fabrica: sessionmaker, Usuario: type, Token: type, rol_por_defecto: Any) -> Auth:
    """Crea las dependencias de autenticación para una app concreta."""

    def obtener_sesion() -> Iterator[Session]:
        """Dependencia FastAPI: abre una transacción por petición. Commit al salir bien,
        rollback si la ruta lanza una excepción.
        """
        # Una transacción por petición: si la ruta falla, se revierte todo.
        with fabrica.begin() as sesion:
            yield sesion

    def usuario_actual(
        authorization: str | None = Header(default=None),
        sesion: Session = Depends(obtener_sesion),
    ) -> Any:
        """Resuelve el usuario a partir de 'Authorization: Bearer <token>'. En la base solo se
        guarda el hash del token, así que se busca por hash; 401 si falta o no
        existe.
        """
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "falta el token Bearer")
        token = sesion.scalar(select(Token).where(Token.token_hash == hash_token(authorization[7:])))
        if token is None:
            raise HTTPException(401, "token inválido")
        return token.usuario

    def requiere_rol(*roles: Any) -> Callable[..., Any]:
        """Devuelve una dependencia que permite solo los ``roles`` indicados."""

        def _verificar(usuario: Any = Depends(usuario_actual)) -> Any:
            """403 si el rol del usuario no está entre los permitidos; si lo está, devuelve el
            usuario a la ruta.
            """
            if usuario.rol not in roles:
                raise HTTPException(403, "rol insuficiente para esta operación")
            return usuario

        return _verificar

    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/registro", status_code=201)
    def registro(datos: RegistroIn, sesion: Session = Depends(obtener_sesion)) -> dict[str, Any]:
        """Alta pública. El rol nunca se acepta del cliente (evita escalada)."""
        email = datos.email.lower()
        if sesion.scalar(select(Usuario).where(Usuario.email == email)):
            raise HTTPException(409, "el email ya está registrado")
        usuario = Usuario(email=email, nombre=datos.nombre,
                          password_hash=hashear_password(datos.password), rol=rol_por_defecto)
        sesion.add(usuario)
        sesion.flush()
        return {"id": usuario.id, "email": usuario.email, "rol": usuario.rol.value}

    @router.post("/login")
    def login(datos: LoginIn, sesion: Session = Depends(obtener_sesion)) -> dict[str, str]:
        """Devuelve un token Bearer si las credenciales son correctas."""
        usuario = sesion.scalar(select(Usuario).where(Usuario.email == datos.email.lower()))
        # Mensaje idéntico para email o contraseña erróneos: no revela cuál falló.
        if usuario is None or not verificar_password(datos.password, usuario.password_hash):
            raise HTTPException(401, "credenciales inválidas")
        token = nuevo_token()
        sesion.add(Token(usuario_id=usuario.id, token_hash=hash_token(token)))
        return {"token": token, "tipo": "Bearer"}

    return Auth(obtener_sesion, usuario_actual, requiere_rol, router)


def crear_usuario(sesion: Session, Usuario: type, email: str, nombre: str, password: str, rol: Any) -> Any:
    """Crea un usuario con un rol concreto (para semillas de admin o tests)."""
    usuario = Usuario(email=email.lower(), nombre=nombre,
                      password_hash=hashear_password(password), rol=rol)
    sesion.add(usuario)
    sesion.flush()
    return usuario
