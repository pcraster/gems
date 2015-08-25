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
    m = Model.query.filter_by(name=model_name).first_or_404()
    
    discretization_name = m.preferred_discretization_name
    d = Discretization.query.filter_by(name=discretization_name).first()
        
    return render_template('modeller/modeller.html', model=m, discretization=d)

