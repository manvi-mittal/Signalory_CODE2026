"""
Application factory.

Run this file directly (`python app.py`) for local development,
or use Gunicorn (`gunicorn app:app`) for deployment.
"""

from flask import Flask
from config import Config
from extensions import db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from auth import auth_bp
    from views import views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)