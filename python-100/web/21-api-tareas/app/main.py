"""API REST de tareas construida con FastAPI.

Endpoints:
    GET    /tareas            -> listar (filtros: completada, buscar, orden, paginación)
    POST   /tareas            -> crear
    GET    /tareas/{id}       -> obtener una
    PUT    /tareas/{id}       -> reemplazar campos editables
    PATCH  /tareas/{id}       -> modificar parcialmente
    DELETE /tareas/{id}       -> borrar
    GET    /estadisticas      -> resumen de pendientes / completadas
"""
from __future__ import annotations

import os
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

# La capa web solo conoce al repositorio, no el SQL.
from app.db import RepositorioTareas


# ---------- Modelos Pydantic (validación de entrada / salida) ----------
class TareaEntrada(BaseModel):
    """Datos para crear o reemplazar una tarea."""
    # Pydantic valida y FastAPI responde 422 automáticamente si algo no cumple.
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(default="", max_length=2000)
    prioridad: int = Field(default=2, ge=1, le=3, description="1=baja, 2=media, 3=alta")
    # date: acepta "AAAA-MM-DD" y rechaza fechas inválidas como "2030-02-31".
    vence: date | None = None
    completada: bool = False


# Todos los campos son opcionales: distingue "no enviado" de "enviado".
class TareaParcial(BaseModel):
    """Datos opcionales para un PATCH: solo se aplican los enviados."""
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = Field(default=None, max_length=2000)
    prioridad: int | None = Field(default=None, ge=1, le=3)
    vence: date | None = None
    completada: bool | None = None


class Tarea(BaseModel):
    """Representación de una tarea devuelta por la API."""
    id: int
    titulo: str
    descripcion: str
    completada: bool
    prioridad: int
    vence: str | None
    creada: str
    actualizada: str


# Patrón "application factory": cada llamada crea una app con su propia base,
# lo que aísla a los tests entre sí.
def crear_app(ruta_db: str | None = None) -> FastAPI:
    """Fábrica de la aplicación: permite inyectar otra base (p. ej. en tests)."""
    app = FastAPI(title="API de Tareas", version="1.0.0")
    # La ruta de la base sale del parámetro, de la variable de entorno o memoria
    repo = RepositorioTareas(ruta_db or os.environ.get("TAREAS_DB", ":memory:"))

    # Inyección de dependencias: los endpoints reciben el repositorio por Depends,
    # lo que permite reemplazarlo con app.dependency_overrides si hiciera falta.
    def obtener_repo() -> RepositorioTareas:
        """Dependencia de FastAPI que entrega el repositorio."""
        return repo

    def _o_404(tarea: dict | None) -> dict:
        """Lanza 404 si la tarea no existe."""
        if tarea is None:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        return tarea

    @app.get("/tareas", response_model=list[Tarea])
    def listar(completada: bool | None = None, buscar: str | None = None,
               # El pattern rechaza con 422 cualquier orden fuera de la lista blanca.
               orden: str = Query("id", pattern="^(id|prioridad|vence)$"),
               # Tope de 200 por página para que nadie pida la tabla entera de una vez.
               limite: int = Query(50, ge=1, le=200), desplazamiento: int = Query(0, ge=0),
               r: RepositorioTareas = Depends(obtener_repo)):
        return r.listar(completada, buscar, orden, limite, desplazamiento)

    @app.post("/tareas", response_model=Tarea, status_code=status.HTTP_201_CREATED)
    def crear(datos: TareaEntrada, r: RepositorioTareas = Depends(obtener_repo)):
        # La fecha se guarda como texto ISO (o NULL si no se envió).
        t = r.crear(datos.titulo, datos.descripcion, datos.prioridad,
                    datos.vence.isoformat() if datos.vence else None)
        # El INSERT siempre crea pendiente; si se pidió completada, se actualiza.
        if datos.completada:
            t = r.actualizar(t["id"], {"completada": True})
        return t

    @app.get("/tareas/{tarea_id}", response_model=Tarea)
    def obtener(tarea_id: int, r: RepositorioTareas = Depends(obtener_repo)):
        return _o_404(r.obtener(tarea_id))

    @app.put("/tareas/{tarea_id}", response_model=Tarea)
    def reemplazar(tarea_id: int, datos: TareaEntrada, r: RepositorioTareas = Depends(obtener_repo)):
        # PUT reemplaza: se mandan todos los campos, incluso los que quedan por defecto.
        cambios = datos.model_dump()
        cambios["vence"] = datos.vence.isoformat() if datos.vence else None
        return _o_404(r.actualizar(tarea_id, cambios))

    @app.patch("/tareas/{tarea_id}", response_model=Tarea)
    def modificar(tarea_id: int, datos: TareaParcial, r: RepositorioTareas = Depends(obtener_repo)):
        # exclude_unset: solo los campos que el cliente realmente envió
        cambios = datos.model_dump(exclude_unset=True)
        # Si mandan "vence": null se respeta (borra la fecha); si mandan fecha, a ISO.
        if cambios.get("vence") is not None:
            cambios["vence"] = cambios["vence"].isoformat()
        return _o_404(r.actualizar(tarea_id, cambios))

    @app.delete("/tareas/{tarea_id}", status_code=status.HTTP_204_NO_CONTENT)
    def borrar(tarea_id: int, r: RepositorioTareas = Depends(obtener_repo)):
        if not r.borrar(tarea_id):
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        # 204 No Content: borrado exitoso, sin cuerpo.
        return Response(status_code=204)

    @app.get("/estadisticas")
    def estadisticas(r: RepositorioTareas = Depends(obtener_repo)):
        return r.estadisticas()

    return app


# Instancia por defecto para `uvicorn app.main:app`
app = crear_app()
