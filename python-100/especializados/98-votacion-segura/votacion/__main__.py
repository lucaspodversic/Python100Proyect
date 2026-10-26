"""``python -m votacion``: levanta la API con uvicorn (extra opcional ``server``)."""
import os

from .api import create_app


def main() -> int:
    try:
        import uvicorn
    except ImportError:  # uvicorn no es dependencia obligatoria
        print("instalá el extra: pip install -e '.[server]'")
        return 2
    # La clave de administración DEBE venir del entorno; sin ella no arrancamos.
    admin = os.environ.get("VOTACION_ADMIN_TOKEN")
    if not admin:
        print("definí VOTACION_ADMIN_TOKEN con un secreto largo")
        return 2
    app = create_app(admin_token=admin, ruta_db=os.environ.get("VOTACION_DB", "votacion.db"))
    uvicorn.run(app, host="127.0.0.1", port=8000)
    return 0


raise SystemExit(main())
