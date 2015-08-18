from flask import Blueprint

modeller=Blueprint('modeller',__name__,template_folder='templates',static_folder='static')

import views
