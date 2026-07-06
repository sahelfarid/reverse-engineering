from . import core  # noqa: F401
from . import devices  # noqa: F401
from . import files  # noqa: F401
from . import shell  # noqa: F401


def register_blueprints(app):
    app.register_blueprint(core.bp)
    app.register_blueprint(devices.bp)
    app.register_blueprint(shell.bp)
    app.register_blueprint(files.bp)
