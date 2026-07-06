from . import app_inspector  # noqa: F401
from . import core  # noqa: F401
from . import devices  # noqa: F401
from . import files  # noqa: F401
from . import logcat  # noqa: F401
from . import packages  # noqa: F401
from . import shell  # noqa: F401


def register_blueprints(app):
    app.register_blueprint(core.bp)
    app.register_blueprint(devices.bp)
    app.register_blueprint(shell.bp)
    app.register_blueprint(files.bp)
    app.register_blueprint(packages.bp)
    app.register_blueprint(app_inspector.bp)
    app.register_blueprint(logcat.bp)
