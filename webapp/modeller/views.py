import os
import re
import subprocess
import uuid
import json

from . import modeller

from flask import g, current_app, render_template, request, jsonify, make_response, render_template
from datetime import datetime, timedelta

from ..models import *

@modeller.route('/<model_name>')
def show_modeller(model_name):
    m=Model.query.filter_by(name=model_name).first_or_404()
    return render_template('modeller/modeller.html',model=m)

#@modeller.route('/<model_name>/<config_key>')
#def show_modeller_with_config(model_name,config_key):
#    m=Model.query.filter_by(name=model_name).first_or_404()
#    mc=ModelConfiguration.query.filter_by(key=config_key).first_or_404()
#    return render_template('modeller/modeller.html',model=m,modelconfiguration=mc)