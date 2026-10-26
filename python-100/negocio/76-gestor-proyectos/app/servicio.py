"""Reglas del gestor de proyectos: permisos por tablero y reordenamiento."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .modelos import NIVEL, Actividad, Lista, Miembro, Permiso, Tablero, Tarjeta, Usuario


class ErrorNegocio(Exception):
    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def permiso_en(s: Session, tablero_id: int, usuario: Usuario) -> Permiso | None:
    """Permiso del usuario en el tablero, o ``None`` si no es miembro."""
    return s.scalar(select(Miembro.permiso).where(Miembro.tablero_id == tablero_id,
                                                  Miembro.usuario_id == usuario.id))


def exigir(s: Session, tablero_id: int, usuario: Usuario, minimo: Permiso) -> Tablero:
    """Devuelve el tablero si el usuario tiene al menos ``minimo``.

    A quien no es miembro se le responde 404 (no se revela que el tablero existe);
    a un miembro con permiso insuficiente, 403.
    """
    tablero = s.get(Tablero, tablero_id)
    permiso = permiso_en(s, tablero_id, usuario) if tablero else None
    if tablero is None or permiso is None:
        raise ErrorNegocio("tablero inexistente", 404)
    if NIVEL[permiso] < NIVEL[minimo]:
        raise ErrorNegocio(f"se requiere permiso '{minimo.value}'", 403)
    return tablero


def registrar(s: Session, tablero_id: int, usuario: Usuario, texto: str) -> None:
    """Agrega una entrada al historial de actividad."""
    s.add(Actividad(tablero_id=tablero_id, usuario_id=usuario.id, texto=texto))


def crear_tablero(s: Session, usuario: Usuario, nombre: str, listas: list[str]) -> Tablero:
    """Crea un tablero; el creador queda como dueño. Admite listas iniciales."""
    t = Tablero(nombre=nombre)
    t.miembros.append(Miembro(usuario_id=usuario.id, permiso=Permiso.DUENIO))
    for i, n in enumerate(listas):
        t.listas.append(Lista(nombre=n, posicion=i))
    s.add(t)
    s.flush()
    registrar(s, t.id, usuario, f"creó el tablero «{nombre}»")
    return t


def agregar_miembro(s: Session, tablero: Tablero, actor: Usuario, email: str, permiso: Permiso) -> Miembro:
    """El dueño invita a otro usuario (por email) con un permiso dado."""
    invitado = s.scalar(select(Usuario).where(Usuario.email == email.lower()))
    if invitado is None:
        raise ErrorNegocio("usuario inexistente", 404)
    existente = s.scalar(select(Miembro).where(Miembro.tablero_id == tablero.id, Miembro.usuario_id == invitado.id))
    if existente is not None:
        if existente.usuario_id == actor.id:
            raise ErrorNegocio("no podés cambiar tu propio permiso", 400)
        existente.permiso = permiso  # actualiza el permiso
        m = existente
    else:
        m = Miembro(tablero_id=tablero.id, usuario_id=invitado.id, permiso=permiso)
        s.add(m)
    registrar(s, tablero.id, actor, f"dio permiso {permiso.value} a {invitado.email}")
    s.flush()
    return m


def _renumerar(elementos: list) -> None:
    """Deja las posiciones contiguas 0..n-1 en el orden actual de la lista."""
    for i, e in enumerate(elementos):
        e.posicion = i


def crear_tarjeta(s: Session, lista: Lista, actor: Usuario, titulo: str, descripcion: str = "",
                  vence: date | None = None, etiquetas: list[str] | None = None) -> Tarjeta:
    """Crea una tarjeta al final de la lista."""
    t = Tarjeta(titulo=titulo, descripcion=descripcion, vence=vence,
                posicion=len(lista.tarjetas), etiquetas=",".join(sorted(set(etiquetas or []))))
    lista.tarjetas.append(t)
    s.flush()
    registrar(s, lista.tablero_id, actor, f"creó la tarjeta «{titulo}» en «{lista.nombre}»")
    return t


def mover_tarjeta(s: Session, tarjeta: Tarjeta, destino: Lista, posicion: int, actor: Usuario) -> Tarjeta:
    """Mueve una tarjeta a ``destino`` en ``posicion`` (se acota a rangos válidos).

    Solo se permite mover dentro del mismo tablero. Ambas listas quedan
    renumeradas sin huecos.
    """
    origen = tarjeta.lista
    if origen.tablero_id != destino.tablero_id:
        raise ErrorNegocio("no se puede mover a otro tablero")
    # Calculamos los órdenes nuevos sin tocar las colecciones ORM: quitar la
    # tarjeta de ``origen.tarjetas`` la marcaría como huérfana y se borraría.
    restantes_origen = [t for t in origen.tarjetas if t is not tarjeta]
    nuevas_destino = [t for t in destino.tarjetas if t is not tarjeta]
    posicion = max(0, min(posicion, len(nuevas_destino)))
    nuevas_destino.insert(posicion, tarjeta)
    if origen.id != destino.id:
        _renumerar(restantes_origen)
    _renumerar(nuevas_destino)
    tarjeta.lista_id = destino.id
    s.flush()
    # Refrescamos las colecciones para que reflejen el nuevo orden.
    s.expire(origen, ["tarjetas"])
    s.expire(destino, ["tarjetas"])
    s.expire(tarjeta, ["lista"])
    if origen.id != destino.id:
        registrar(s, destino.tablero_id, actor, f"movió «{tarjeta.titulo}» de «{origen.nombre}» a «{destino.nombre}»")
    return tarjeta


def mover_lista(s: Session, tablero: Tablero, lista: Lista, posicion: int) -> None:
    """Reordena una lista dentro del tablero."""
    tablero.listas.remove(lista)
    tablero.listas.insert(max(0, min(posicion, len(tablero.listas))), lista)
    _renumerar(tablero.listas)
    s.flush()


def asignar(s: Session, tarjeta: Tarjeta, usuario_id: int | None, actor: Usuario) -> Tarjeta:
    """Asigna la tarjeta a un miembro del tablero (o la desasigna con ``None``)."""
    tablero_id = tarjeta.lista.tablero_id
    if usuario_id is not None:
        miembro = s.scalar(select(Miembro).where(Miembro.tablero_id == tablero_id, Miembro.usuario_id == usuario_id))
        if miembro is None or miembro.permiso == Permiso.LECTOR:
            raise ErrorNegocio("solo se puede asignar a editores o dueños del tablero")
    tarjeta.asignado_id = usuario_id
    registrar(s, tablero_id, actor, f"asignó «{tarjeta.titulo}»")
    return tarjeta


def vencidas(s: Session, tablero: Tablero, hoy: date) -> list[Tarjeta]:
    """Tarjetas con fecha de vencimiento anterior a hoy."""
    return [t for l in tablero.listas for t in l.tarjetas if t.vence is not None and t.vence < hoy]
