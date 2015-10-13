from flask import Blueprint

install = Blueprint('install', __name__, template_folder='templates', static_folder='static')

import views
