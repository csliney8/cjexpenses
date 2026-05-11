from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from flask_login import LoginManager
import os

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

db = SQLAlchemy()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])
login_manager = LoginManager()


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    CORS(app)

    # Database
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/expensedb",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    # Session cookie settings
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # NOTE: SESSION_COOKIE_SECURE = True should be set when serving over HTTPS

    # AWS settings
    app.config["S3_BUCKET"] = os.environ.get("S3_BUCKET", "")
    app.config["AWS_REGION"] = os.environ.get("AWS_REGION", "us-east-1")

    # Extensions
    db.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    # User loader for Flask-Login
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Blueprints
    from app.routes.expenses import expenses_bp
    from app.routes.uploads import uploads_bp
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(expenses_bp, url_prefix="/api")
    app.register_blueprint(uploads_bp, url_prefix="/api")

    @app.errorhandler(413)
    def file_too_large(_):
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        return jsonify({"error": f"File too large. Max size is {mb} MB."}), 413

    # Create tables on first launch
    with app.app_context():
        db.create_all()

    return app
