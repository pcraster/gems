from flask import Blueprint

status=Blueprint('status',__name__,template_folder='templates',static_folder='static')

import views
