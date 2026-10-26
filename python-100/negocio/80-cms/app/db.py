"""Configuración de la base de datos.

Usamos SQLite porque es liviano y no requiere servidor. El punto delicado es la
**concurrencia**: dos clientes podrían comprobar "la habitación está libre" al
mismo tiempo y ambos insertar una reserva. Para evitarlo, cada transacción se
abre con ``BEGIN IMMEDIATE``, que toma el bloqueo de escritura de SQLite desde
el principio. Así la secuencia "comprobar solapamiento + insertar" es atómica:
la segunda transacción espera (``timeout``) hasta que la primera termina y
entonces ve la reserva ya creada.

Es la receta documentada por SQLAlchemy para controlar el ``BEGIN`` de pysqlite.
"""
from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Clase base declarativa de la que heredan todos los modelos ORM."""


def crear_motor(url: str) -> Engine:
    """Crea el motor SQLAlchemy con el modo transaccional seguro.

    Args:
        url: URL de conexión, por ejemplo ``sqlite:///hotel.db``.

    Returns:
        Un ``Engine`` listo para usar desde varios hilos.
    """
    motor = create_engine(
        url,
        # check_same_thread=False: FastAPI atiende peticiones en varios hilos.
        # timeout=30: segundos que una conexión espera si la BD está bloqueada.
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(motor, "connect")
    def _al_conectar(conexion_dbapi, _registro) -> None:  # type: ignore[no-untyped-def]
        """Por cada conexión nueva: desactiva el BEGIN implícito del driver (lo emitimos
        nosotros) y activa las claves foráneas, que SQLite trae apagadas.
        """
        # Desactivamos el BEGIN automático del driver para emitirlo nosotros.
        conexion_dbapi.isolation_level = None
        cursor = conexion_dbapi.cursor()
        # Integridad referencial: SQLite no la activa por defecto.
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(motor, "begin")
    def _al_comenzar(conexion) -> None:  # type: ignore[no-untyped-def]
        """Cada transacción empieza con BEGIN IMMEDIATE: toma el bloqueo de escritura desde el
        principio y así 'leer y después escribir' es atómico frente a otras
        peticiones.
        """
        # BEGIN IMMEDIATE = bloqueo de escritura desde el inicio de la transacción.
        conexion.exec_driver_sql("BEGIN IMMEDIATE")

    return motor


def crear_fabrica_sesiones(motor: Engine) -> sessionmaker:
    """Devuelve una fábrica de sesiones ligada al motor.

    ``expire_on_commit=False`` permite seguir leyendo los objetos después del
    commit (útil para serializarlos en la respuesta HTTP).
    """
    return sessionmaker(bind=motor, expire_on_commit=False)
