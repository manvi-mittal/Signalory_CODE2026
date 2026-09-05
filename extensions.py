"""
Flask extensions are created here, uninitialized, and attached to the
app later in app.py via `.init_app(app)`.

Why this file exists: models.py needs `db`, app.py needs `db` too, and
routes need both `db` and `login_manager`. If we created these directly
inside app.py, every other file that needs them would have to import
app.py itself, and app.py imports models/routes -> circular import.
This tiny file breaks that cycle.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
