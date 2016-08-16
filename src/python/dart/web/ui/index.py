from flask import Blueprint, render_template
from dart.web.api.entity_lookup import check_login

index_bp = Blueprint('index', __name__)


@index_bp.route('/')
@check_login
def index():
    return render_template('index.html')


@index_bp.route('/info')
def info():
    return render_template('info.html')