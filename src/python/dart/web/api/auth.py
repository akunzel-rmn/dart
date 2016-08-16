import json
import hashlib
import hmac

from flask import Blueprint, request, current_app, make_response, redirect, flash, url_for, render_template
from flask.ext.login import login_required, LoginManager, UserMixin, login_user, logout_user
from urlparse import urlparse
from datetime import datetime, timedelta
from dateutil.parser import parse

from dart.service.user import UserService
from dart.service.api_key import ApiKeyService
from dart.model.exception import DartAuthenticationException

auth_bp = Blueprint('auth', __name__)

login_manager = LoginManager()

@auth_bp.route('/login', methods=['GET'])
@login_manager.unauthorized_handler
def get_login():
    auth = current_app.auth_class(request)
    return auth.handle_login_request()

@auth_bp.route('/login', methods=['POST'])
def post_login():
    auth = current_app.auth_class(request)
    user = auth.process_login_response()
    if user.is_authenticated:
        login_user(user)
        return redirect(request.args.get('next') or '/')
    flash('Login incorrect')
    return redirect(url_for('auth.get_login'))

@auth_bp.route('/logout', methods=['GET'])
def logout():
    auth = current_app.auth_class(request)
    auth.handle_logout_request()
    logout_user()
    flash('logged out')
    return render_template('info.html')

@login_manager.user_loader
def load_user(user_id):
    user_service = current_app.dart_context.get(UserService)
    user = user_service.get_user(user_id, False)
    user.is_authenticated = (user.is_authenticated and user.session_expiration > datetime.utcnow())
    return user

@login_manager.request_loader
def api_auth(request):
    auth_header = request.headers.get('Authorization')
    request_timestamp = request.headers.get('x-dart-date')
    if not (auth_header and request_timestamp):
        # if these headers are missing then the API call is coming from the UI
        # and the request should load the user from the session cookie
        return None
    auth_data = {item.split('=')[0]: item.split('=')[1] for item in auth_header.split()}

    assert 'Credential' in auth_data
    assert 'Signature' in auth_data

    api_key_service = current_app.dart_context.get(ApiKeyService)
    user_service = current_app.dart_context.get(UserService)

    api_key = api_key_service.get_api_key(auth_data['Credential'])
    if not api_key:
        raise DartAuthenticationException('DART is unable to authenticate your request')

    user = user_service.get_user(api_key.user_id, False)
    if not user:
        raise DartAuthenticationException('DART is unable to authenticate your request')

    user.is_authenticated = \
        datetime.utcnow() > (parse(request_timestamp) - timedelta(hours=1)) and \
        auth_data['Signature'] == hmac.new(key=api_key.api_key,
                                           msg='{}{}'.format(request_timestamp, api_key.api_secret),
                                           digestmod=hashlib.sha256).hexdigest()

    if not user.is_authenticated:
        raise DartAuthenticationException('DART is unable to authenticate your request')
    return user
