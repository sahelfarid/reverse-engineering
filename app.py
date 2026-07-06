from flask import Flask

import auth
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
    register_blueprints(app)
    return app


app = create_app()


if __name__ == "__main__":
    plaintext_password = auth.ensure_password()
    if plaintext_password:
        print("=" * 60)
        print("First run: generated a login password for the ADB panel.")
        print(f"  Password: {plaintext_password}")
        print("It is stored (hashed) in data/settings.json — change it")
        print("later from the Settings tab.")
        print("=" * 60)
    # threaded=True: background jobs + SSE (logcat) streams need concurrent
    # requests, which the dev server won't serve otherwise.
    # Local developer tool only: it can run a root shell and read/write
    # device files, so it must never bind anything but loopback.
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
