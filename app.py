from datetime import timedelta

from flask import Flask

import config
from routes import register_blueprints


def create_app() -> Flask:
    # Resolve templates/static through config's frozen-aware paths instead of
    # Flask's default relative-to-__file__ lookup, which breaks once the app is
    # packaged (assets live in the PyInstaller extraction dir, not next to a
    # frozen executable).
    app = Flask(
        __name__,
        template_folder=str(config.TEMPLATE_DIR),
        static_folder=str(config.STATIC_DIR),
    )
    app.secret_key = config.generate_secret_key()
    # Only takes effect for sessions marked session.permanent = True (the
    # "remember me" login option); a normal login stays a browser-session cookie.
    app.permanent_session_lifetime = timedelta(days=30)
    register_blueprints(app)
    return app


app = create_app()


if __name__ == "__main__":
    # No first-run password is generated here anymore -- the first-launch
    # setup screen (served by routes.core.index()) lets the user set one
    # (or explicitly skip) from the browser instead of reading it off stdout.
    # threaded=True: background jobs + SSE (logcat) streams need concurrent
    # requests, which the dev server won't serve otherwise.
    # Local developer tool only: it can run a root shell and read/write
    # device files, so it must never bind anything but loopback.
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
