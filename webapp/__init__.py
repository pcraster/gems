from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.uuid import FlaskUUID

from flask.ext.user import UserManager, UserMixin, SQLAlchemyAdapter
from flask.ext.user import current_user, login_required, roles_required, UserMixin

from flask import g

from .api import api
from .data import data
from .modeller import modeller
from .site import site
from .admin import admin
from .status import status
from .install import install

app = Flask(__name__)

#g.test = "lala"

FlaskUUID(app)

#Load the base configuration from settings.py
app.config.from_object('webapp.settings')

#Overwrite any settings with local_settings.py
try: app.config.from_object('webapp.local_settings')
except: print " * Local settings file coult not be imported."

from models import *

db.init_app(app)

@app.context_processor
def system_status():
    """
    This context processor makes the "system_status" variable available in all
    the templates.
    """
    status = {
        'beanstalk_workers': beanstalk.workers
    }
    return dict(system_status=status)

db_adapter = SQLAlchemyAdapter(db,  User)
user_manager = UserManager(db_adapter, app)

app.register_blueprint(modeller,    url_prefix='/modeller')
app.register_blueprint(data,        url_prefix='/data')
app.register_blueprint(api,         url_prefix='/api/v1')
app.register_blueprint(admin,       url_prefix='/admin')
app.register_blueprint(status,      url_prefix='/status')
app.register_blueprint(install,     url_prefix='/install')
app.register_blueprint(site)

if __name__ == "__main__":
	app.run()

