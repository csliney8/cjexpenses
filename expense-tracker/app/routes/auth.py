from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from email_validator import validate_email, EmailNotValidError
from app import db, limiter
from app.models import User

auth_bp = Blueprint("auth", __name__)


# Register page
@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        # Validate email format
        try:
            validated = validate_email(email, check_deliverability=False)
            email = validated.normalized
        except EmailNotValidError:
            flash("Please enter a valid email address.", "error")
            return render_template("register.html"), 400

        # Validate password
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html"), 400
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html"), 400

        # Check uniqueness
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_template("register.html"), 400

        # Create user
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Auto-login after register
        login_user(user)
        return redirect(url_for("main.index"))

    return render_template("register.html")


# Login page
@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("login.html"), 401

        login_user(user)
        return redirect(url_for("main.index"))

    return render_template("login.html")


# Logout
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# Optional API endpoint — useful if frontend wants to know who's logged in
@auth_bp.route("/me")
@login_required
def me():
    return jsonify(current_user.to_dict())