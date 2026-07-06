from . import app_inspector  # noqa: F401
from . import automation  # noqa: F401
from . import backup  # noqa: F401
from . import battery  # noqa: F401
from . import core  # noqa: F401
from . import devices  # noqa: F401
from . import files  # noqa: F401
from . import jobs  # noqa: F401
from . import logcat  # noqa: F401
from . import network  # noqa: F401
from . import packages  # noqa: F401
from . import process_manager  # noqa: F401
from . import properties  # noqa: F401
from . import screen  # noqa: F401
from . import shell  # noqa: F401


def register_blueprints(app):
    app.register_blueprint(core.bp)
    app.register_blueprint(devices.bp)
    app.register_blueprint(shell.bp)
    app.register_blueprint(files.bp)
    app.register_blueprint(packages.bp)
    app.register_blueprint(app_inspector.bp)
    app.register_blueprint(logcat.bp)
    app.register_blueprint(screen.bp)
    app.register_blueprint(automation.bp)
    app.register_blueprint(properties.bp)
    app.register_blueprint(network.bp)
    app.register_blueprint(backup.bp)
    app.register_blueprint(battery.bp)
    app.register_blueprint(process_manager.bp)
    app.register_blueprint(jobs.bp)
