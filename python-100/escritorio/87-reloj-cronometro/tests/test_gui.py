"""Test de humo de la GUI con relojes falsos (se omite sin pantalla)."""
from datetime import datetime


def test_gui_importable():
    """Importar la GUI no crea ventanas ni requiere pantalla."""
    import reloj.gui as g

    assert callable(g.main)


def test_gui_temporizador_y_alarma(raiz):
    """Con relojes falsos. Temporizador de 10 s: en t=4.2 faltan 5.8 s y se muestra 00:00:06
    (se redondea hacia arriba, como cualquier cuenta regresiva). En t=10 avisa una sola
    vez aunque se actualice dos veces. Alarma 07:00 suena a las 07:00:05. Cronómetro
    iniciado en t=10 con vuelta en t=12.5 → 2.50 s.
    """
    from reloj.gui import AppReloj

    mono = [0.0]
    pared = [datetime(2026, 3, 1, 6, 59, 50)]
    avisos = []
    app = AppReloj(raiz, ahora=lambda: pared[0], monotonico=lambda: mono[0], avisar=avisos.append)
    assert app.txt_reloj.get() == "06:59:50"

    app.entrada_temp.set("10")
    app.temp_alternar()
    mono[0] = 4.2
    app.actualizar()
    assert app.txt_temp.get() == "00:00:06"
    mono[0] = 10.0
    app.actualizar(); app.actualizar()
    assert avisos == ["¡Tiempo cumplido!"]

    app.entrada_alarma.set("07:00"); app.etiqueta_alarma.set("Café")
    app.agregar_alarma()
    pared[0] = datetime(2026, 3, 1, 7, 0, 5)
    app.actualizar()
    assert avisos[-1] == "Alarma 07:00 Café"

    app.crono_alternar(); mono[0] = 12.5; app.crono_vuelta()
    assert app.lista_vueltas.get(0) == "Vuelta 1: 00:00:02.50"
