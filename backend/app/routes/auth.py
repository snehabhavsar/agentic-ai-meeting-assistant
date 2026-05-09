from flask import Blueprint, request, redirect, url_for, render_template
from flask_login import login_user, logout_user, current_user

from ..db import db
from ..models import User


bp = Blueprint("auth", __name__)


# ── UI routes ─────────────────────────────────────────────────

@bp.get("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("ui.index"))
    return render_template("auth.html", tab="login")


@bp.get("/signup")
def signup_page():
    if current_user.is_authenticated:
        return redirect(url_for("ui.index"))
    return render_template("auth.html", tab="signup")


# ── API routes ────────────────────────────────────────────────

@bp.post("/auth/signup")
def signup():
    payload = request.get_json(force=True, silent=True) or {}
    name     = (payload.get("name")     or "").strip()
    email    = (payload.get("email")    or "").strip().lower()
    password =  payload.get("password") or ""

    if not name:
        return {"error": "Name is required"}, 400
    if not email or "@" not in email:
        return {"error": "Valid email is required"}, 400
    if len(password) < 8:
        return {"error": "Password must be at least 8 characters"}, 400

    if User.query.filter_by(email=email).first():
        return {"error": "An account with this email already exists"}, 409

    user = User(name=name, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user, remember=True)
    return {"user": user.to_dict()}, 201


@bp.post("/auth/login")
def login():
    payload  = request.get_json(force=True, silent=True) or {}
    email    = (payload.get("email")    or "").strip().lower()
    password =  payload.get("password") or ""

    if not email or not password:
        return {"error": "Email and password are required"}, 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return {"error": "Invalid email or password"}, 401

    login_user(user, remember=payload.get("remember", True))
    return {"user": user.to_dict()}


@bp.post("/auth/logout")
def logout():
    logout_user()
    return {"success": True}


@bp.get("/auth/me")
def me():
    if not current_user.is_authenticated:
        return {"error": "Authentication required", "code": "UNAUTHENTICATED"}, 401
    return {"user": current_user.to_dict()}
