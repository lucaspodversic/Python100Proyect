"""Test de humo de la GUI (se omite sin pantalla)."""
from boveda.cripto import ParametrosKdf
from boveda.modelo import Boveda
from boveda.portapapeles import PortapapelesFalso

KDF = ParametrosKdf(n=2**10)


def test_gui_importable():
    """Importar la GUI no crea ventanas ni requiere pantalla."""
    import boveda.gui as g

    assert callable(g.main)


def test_gui_flujo_completo(raiz, tmp_path):
    """Crear (rechaza confirmación distinta), agregar una entrada desde el diálogo, copiar la
    contraseña, bloquear por inactividad adelantando el reloj (limpia el portapapeles) y
    reintentar con una maestra incorrecta.
    """
    from boveda import gui

    ruta = tmp_path / "v.boveda"
    pp = PortapapelesFalso()
    t = [0.0]
    app = gui.AppBoveda(raiz, ruta, KDF, pp, reloj=lambda: t[0])
    app.var_maestra.set("una maestra larga"); app.var_repetir.set("otra")
    assert not app.desbloquear() and "no coinciden" in app.estado.get()
    app.var_maestra.set("una maestra larga"); app.var_repetir.set("una maestra larga")
    assert app.desbloquear() and ruta.exists()

    dlg = app.editar(None)
    dlg.vars["sitio"].set("Correo"); dlg.vars["usuario"].set("yo"); dlg.vars["clave"].set("Kq9!vP2#mZ7$")
    dlg.aceptar()
    assert app.tabla.get_children() and Boveda.abrir(ruta, "una maestra larga").entradas[0].sitio == "Correo"

    app.tabla.selection_set(app.tabla.get_children()[0])
    app.copiar_clave_sel()
    assert pp.contenido == "Kq9!vP2#mZ7$"

    t[0] = gui.INACTIVIDAD_S + 1
    app._vigilar()                         # bloqueo por inactividad
    assert app.boveda is None and pp.contenido == "" and app.estado.get() == "Bóveda bloqueada"
    app.var_maestra.set("mal mal mal mal")
    assert not app.desbloquear() and "incorrecta" in app.estado.get()
