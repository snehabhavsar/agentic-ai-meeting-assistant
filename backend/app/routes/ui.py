import json

from flask import Blueprint, render_template
from flask_login import login_required, current_user


bp = Blueprint("ui", __name__)


@bp.get("/")
@login_required
def index():
    user_json = json.dumps(current_user.to_dict())
    return render_template("index.html", user_json=user_json)
