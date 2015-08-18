from flask import Blueprint

admin=Blueprint('admin',__name__,template_folder='templates',static_folder='static')

#@admin.before_request
#def restrict_to_admin_roles():
#    if not user.is_admin:
#        return redirect(...)

import views
