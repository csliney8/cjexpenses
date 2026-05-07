from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
import os

db = SQLAlchemy()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="../static")
    CORS(app)

    # ── Database ──────────────────────────────────────────────────────────────
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/expensedb",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # ── AWS settings (read from env, never hardcoded) ─────────────────────────
    app.config["S3_BUCKET"] = os.environ.get("S3_BUCKET", "")
    app.config["AWS_REGION"] = os.environ.get("AWS_REGION", "us-east-1")

    # ── Extensions ────────────────────────────────────────────────────────────
    db.init_app(app)
    limiter.init_app(app)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from app.routes.expenses import expenses_bp
    from app.routes.uploads import uploads_bp
    from app.routes.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(expenses_bp, url_prefix="/api")
    app.register_blueprint(uploads_bp, url_prefix="/api")

    # ── Create tables on first launch ────────────────────────────────────────
    with app.app_context():
        db.create_all()

    return app
