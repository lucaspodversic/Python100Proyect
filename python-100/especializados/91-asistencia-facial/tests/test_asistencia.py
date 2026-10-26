"""Tests con embeddings sintéticos deterministas (sin cámara, sin modelos y sin fotos de
personas reales).
"""
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from asistencia.galeria import Consentimiento, Galeria
from asistencia.pipeline import ExtractorSintetico, embedding_base, normalizar
from asistencia.registro import Registro
from asistencia.sistema import Sistema

OK = Consentimiento("RRHH + interesado", "2026-10-01T09:00:00")


def muestras(nombre, n=4, semilla=1):
    """n embeddings de la misma identidad con ruido distinto."""
    ext = ExtractorSintetico(semilla=semilla)
    return [ext.extraer([nombre])[0].embedding for _ in range(n)]


@pytest.fixture
def galeria():
    """Galería con ana, beto y carla registrados con consentimiento."""
    g = Galeria()
    for p in ("ana", "beto", "carla"):
        g.registrar(p, muestras(p), OK)
    return g


def test_sintetico_determinista():
    """Misma semilla → mismos vectores; los embeddings tienen norma 1."""
    a = ExtractorSintetico(semilla=5).extraer(["ana", "beto"])
    b = ExtractorSintetico(semilla=5).extraer(["ana", "beto"])
    assert len(a) == 2 and np.allclose(a[0].embedding, b[0].embedding)
    assert abs(np.linalg.norm(a[0].embedding) - 1) < 1e-9


def test_registro_exige_consentimiento_y_muestras():
    """Sin consentimiento o con firmante en blanco → PermissionError; con 2 muestras (mínimo 3)
    → ValueError.
    """
    g = Galeria()
    with pytest.raises(PermissionError):
        g.registrar("ana", muestras("ana"), None)
    with pytest.raises(PermissionError):
        g.registrar("ana", muestras("ana"), Consentimiento(" ", "x"))
    with pytest.raises(ValueError, match="al menos"):
        g.registrar("ana", muestras("ana", n=2), OK)


def test_registro_rechaza_muestras_mezcladas():
    """Mezclar muestras de ana y beto se detecta como inconsistente."""
    with pytest.raises(ValueError, match="inconsistentes"):
        Galeria().registrar("ana", muestras("ana", 2) + muestras("beto", 2), OK)


def test_identifica_y_rechaza_desconocido(galeria):
    """Una foto nueva de beto (otra semilla de ruido) se reconoce; alguien no registrado queda
    como desconocido.
    """
    ext = ExtractorSintetico(semilla=99)
    assert galeria.identificar(ext.extraer(["beto"])[0].embedding).persona == "beto"
    r = galeria.identificar(ext.extraer(["intruso"])[0].embedding)
    assert r.persona is None and r.motivo == "sin coincidencia"


def test_ambiguo_no_identifica(galeria):
    """Un vector a mitad de camino entre ana y beto está casi a la misma distancia de ambos
    (diferencia < margen 0.1) → ambiguo. Se usa umbral 1.2 para que el rechazo sea por
    ambigüedad y no por distancia.
    """
    # Punto medio entre ana y beto: cerca de ambos → "ambiguo" (con umbral laxo).
    g = Galeria(umbral=1.2)
    g._centroides = dict(galeria._centroides)
    medio = normalizar(embedding_base("ana") + embedding_base("beto"))
    assert g.identificar(medio).motivo == "ambiguo"


def test_olvidar_y_persistencia(galeria, tmp_path):
    """Guardar y cargar conserva personas e identificación; olvidar borra y es idempotente (la
    segunda vez devuelve False).
    """
    ruta = tmp_path / "g.json"
    galeria.guardar(ruta)
    g2 = Galeria.cargar(ruta)
    assert g2.personas() == ["ana", "beto", "carla"]
    assert g2.identificar(embedding_base("carla")).persona == "carla"
    assert g2.olvidar("carla") and "carla" not in g2 and not g2.olvidar("carla")


def test_registro_alterna_y_antirrebote():
    """09:00 entrada; 09:00:30 ignorado (antirrebote de 2 min); 13:00 salida; 14:00 entrada;
    17:30 salida. Horas = 4 (9→13) + 3.5 (14→17:30) = 7.5 con 4 fichajes.
    """
    r = Registro()
    t = datetime(2026, 10, 26, 9, 0)
    assert r.marcar("ana", t).tipo == "entrada"
    assert r.marcar("ana", t + timedelta(seconds=30)) is None
    assert r.marcar("ana", t + timedelta(hours=4)).tipo == "salida"
    assert r.marcar("ana", t + timedelta(hours=5)).tipo == "entrada"
    assert r.marcar("ana", t + timedelta(hours=8, minutes=30)).tipo == "salida"
    inf = r.informe_dia(date(2026, 10, 26))
    assert inf["ana"] == {"horas": 7.5, "sin_salida": False, "fichajes": 4}


def test_salida_olvidada_y_nuevo_dia():
    """Si beto no fichó salida, al día siguiente arranca con 'entrada' y el informe del día
    anterior lo marca como 'sin salida'.
    """
    r = Registro()
    r.marcar("beto", datetime(2026, 10, 26, 9, 0))
    assert r.marcar("beto", datetime(2026, 10, 27, 9, 0)).tipo == "entrada"
    assert r.informe_dia(date(2026, 10, 26))["beto"]["sin_salida"]


def test_purgar_y_olvidar(tmp_path):
    """Purgar antes de 2026 borra solo el fichaje de 2025; olvidar a beto borra su único
    fichaje.
    """
    r = Registro(tmp_path / "a.db")
    r.marcar("ana", datetime(2025, 1, 1, 9))
    r.marcar("ana", datetime(2026, 10, 26, 9))
    r.marcar("beto", datetime(2026, 10, 26, 9))
    assert r.purgar(datetime(2026, 1, 1)) == 1
    assert r.olvidar("beto") == 1
    r.cerrar()


def test_sistema_confirma_tras_n_fotogramas(galeria):
    """Con 3 confirmaciones, ana ficha entrada en el 3.º fotograma y no se repite en el 4.º; el
    intruso suma 1 desconocido. Tras salir de cuadro hacen falta otros 3 fotogramas, que
    generan la salida (el reloj avanza 10 min por llamada, así que no hay antirrebote).
    """
    reloj = iter(datetime(2026, 10, 26, 9, 0) + timedelta(minutes=m) for m in range(0, 1000, 10))
    s = Sistema(ExtractorSintetico(semilla=3), galeria, Registro(), confirmaciones=3, reloj=lambda: next(reloj))
    assert s.procesar(["ana", "intruso"]) == []
    assert s.procesar(["ana"]) == []
    eventos = s.procesar(["ana"])
    assert [(e.persona, e.tipo) for e in eventos] == [("ana", "entrada")]
    assert s.procesar(["ana"]) == []           # la racha sigue: no repite
    assert s.desconocidos == 1
    s.procesar([])                             # sale de cuadro → reinicia racha
    for _ in range(3):
        eventos = s.procesar(["ana"])
    assert eventos[0].tipo == "salida"


def test_sistema_olvidar(galeria):
    """Olvidar elimina a beto de la galería y del registro, y deja de reconocerlo."""
    s = Sistema(ExtractorSintetico(), galeria, Registro(), confirmaciones=1,
                reloj=lambda: datetime(2026, 10, 26, 9))
    s.procesar(["beto"])
    s.olvidar("beto")
    assert "beto" not in galeria and s.registro.ultimo("beto") is None
    assert s.procesar(["beto"]) == []
