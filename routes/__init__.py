from . import core  # noqa: F401


def register_blueprints(app):
    app.register_blueprint(core.bp)
