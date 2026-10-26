"""API REST de RRHH.

Permisos:
- ``empleado``: ve su legajo (``/yo``), pide ausencias y consulta sus nóminas.
- ``rrhh``: alta/baja de empleados, resolución de ausencias, liquidación.
- ``admin``: todo lo anterior y asignación de roles.

Por privacidad, un empleado nunca ve el salario de otro.
"""
from __future__ import annotations

import os
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import servicio
from .auth import crear_auth, crear_usuario
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Ausencia, Empleado, Nomina, Rol, TipoAusencia, Token, Usuario


class EmpleadoIn(BaseModel):
    legajo: str = Field(pattern=r"^[A-Z0-9-]{1,20}$")
    nombre: str = Field(min_length=1, max_length=120)
    departamento: str = Field(min_length=1, max_length=60)
    puesto: str = Field(min_length=1, max_length=60)
    fecha_ingreso: date
    salario_bruto_centavos: int = Field(gt=0)
    dias_vacaciones_anuales: int = Field(default=14, ge=0, le=60)
    usuario_id: int | None = None


class EmpleadoOut(EmpleadoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool


class AusenciaIn(BaseModel):
    tipo: TipoAusencia
    desde: date
    hasta: date


class AusenciaOut(AusenciaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empleado_id: int
    estado: str
    dias: int


class NominaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    empleado_id: int
    periodo: str
    bruto_centavos: int
    descuento_ausencias_centavos: int
    aportes_centavos: int
    neto_centavos: int


class RolIn(BaseModel):
    rol: Rol


def crear_app(url_bd: str = "sqlite:///rrhh.db", admin_email: str = "admin@rrhh.local",
              admin_password: str | None = None) -> FastAPI:
    """Fábrica de la aplicación (BD propia por instancia)."""
    app = FastAPI(title="RRHH", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    fabrica = crear_fabrica_sesiones(motor)
    password = admin_password or os.environ.get("RRHH_ADMIN_PASSWORD")
    if password:
        with fabrica.begin() as s:
            if s.scalar(select(Usuario).where(Usuario.email == admin_email)) is None:
                crear_usuario(s, Usuario, admin_email, "Admin", password, Rol.ADMIN)

    auth = crear_auth(fabrica, Usuario, Token, Rol.EMPLEADO)
    app.include_router(auth.router)
    S = Depends(auth.obtener_sesion)
    yo = Depends(auth.usuario_actual)
    gestion = Depends(auth.requiere_rol(Rol.RRHH, Rol.ADMIN))
    admin = Depends(auth.requiere_rol(Rol.ADMIN))

    @app.exception_handler(servicio.ErrorNegocio)
    async def _err(_r: Request, e: servicio.ErrorNegocio) -> JSONResponse:
        """Traduce ErrorNegocio a una respuesta JSON con su código y {'detail': mensaje}, el
        mismo formato que usan las HTTPException de FastAPI.
        """
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    def legajo_de(s: Session, u: Usuario) -> Empleado:
        """Devuelve el legajo vinculado al usuario o 404."""
        emp = s.scalar(select(Empleado).where(Empleado.usuario_id == u.id))
        if emp is None:
            raise HTTPException(404, "tu usuario no está vinculado a un legajo")
        return emp

    @app.patch("/usuarios/{uid}/rol", dependencies=[admin])
    def cambiar_rol(uid: int, d: RolIn, s: Session = S) -> dict:
        u = s.get(Usuario, uid)
        if u is None:
            raise HTTPException(404, "usuario inexistente")
        u.rol = d.rol
        return {"id": uid, "rol": d.rol.value}

    @app.post("/empleados", response_model=EmpleadoOut, status_code=201, dependencies=[gestion])
    def alta(d: EmpleadoIn, s: Session = S) -> Empleado:
        e = Empleado(**d.model_dump())
        s.add(e)
        try:
            s.flush()
        except IntegrityError:
            raise HTTPException(409, "legajo o usuario ya asignado") from None
        return e

    @app.get("/empleados", response_model=list[EmpleadoOut], dependencies=[gestion])
    def listar(departamento: str | None = None, s: Session = S) -> list[Empleado]:
        q = select(Empleado).order_by(Empleado.legajo)
        if departamento:
            q = q.where(Empleado.departamento == departamento)
        return list(s.scalars(q))

    @app.post("/empleados/{eid}/baja", response_model=EmpleadoOut, dependencies=[gestion])
    def baja(eid: int, s: Session = S) -> Empleado:
        """Baja lógica: se conserva el historial (no se borra el legajo)."""
        e = s.get(Empleado, eid)
        if e is None:
            raise HTTPException(404, "empleado inexistente")
        e.activo = False
        return e

    @app.get("/yo", response_model=EmpleadoOut)
    def mi_legajo(u: Usuario = yo, s: Session = S) -> Empleado:
        return legajo_de(s, u)

    @app.post("/yo/ausencias", response_model=AusenciaOut, status_code=201)
    def pedir_ausencia(d: AusenciaIn, u: Usuario = yo, s: Session = S) -> Ausencia:
        return servicio.solicitar_ausencia(s, legajo_de(s, u), d.tipo, d.desde, d.hasta)

    @app.get("/yo/vacaciones")
    def saldo(anio: int, u: Usuario = yo, s: Session = S) -> dict:
        emp = legajo_de(s, u)
        usados = servicio.dias_vacaciones_usados(s, emp.id, anio)
        return {"anio": anio, "usados": usados, "disponibles": emp.dias_vacaciones_anuales - usados}

    @app.get("/yo/nominas", response_model=list[NominaOut])
    def mis_nominas(u: Usuario = yo, s: Session = S) -> list[Nomina]:
        emp = legajo_de(s, u)
        return list(s.scalars(select(Nomina).where(Nomina.empleado_id == emp.id).order_by(Nomina.periodo)))

    @app.get("/ausencias", response_model=list[AusenciaOut], dependencies=[gestion])
    def pendientes(estado: str = "solicitada", s: Session = S) -> list[Ausencia]:
        return list(s.scalars(select(Ausencia).where(Ausencia.estado == estado).order_by(Ausencia.desde)))

    @app.post("/ausencias/{aid}/aprobar", response_model=AusenciaOut)
    def aprobar(aid: int, u: Usuario = gestion, s: Session = S) -> Ausencia:
        return servicio.resolver_ausencia(s, aid, u, True)

    @app.post("/ausencias/{aid}/rechazar", response_model=AusenciaOut)
    def rechazar(aid: int, u: Usuario = gestion, s: Session = S) -> Ausencia:
        return servicio.resolver_ausencia(s, aid, u, False)

    @app.post("/nominas/{periodo}", response_model=list[NominaOut], status_code=201, dependencies=[gestion])
    def liquidar(periodo: str, s: Session = S) -> list[Nomina]:
        return servicio.liquidar_periodo(s, periodo)

    @app.get("/reportes/masa-salarial", dependencies=[gestion])
    def masa(s: Session = S) -> dict[str, int]:
        return servicio.masa_salarial_por_departamento(s)

    return app


def __getattr__(nombre: str):  # pragma: no cover - instancia perezosa para uvicorn
    """Atributo perezoso del módulo: ``uvicorn app.main:app`` pide ``app`` y recién ahí se
    crea, así importar el módulo (por ejemplo en los tests) no abre ninguna base.
    """
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
