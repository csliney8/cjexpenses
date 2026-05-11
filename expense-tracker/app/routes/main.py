from flask import Blueprint, render_template
from flask_login import login_required, current_user

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    return render_template("index.html", current_user=current_user)


@main_bp.route("/health")
def health():
    return {"status": "ok"}, 200
