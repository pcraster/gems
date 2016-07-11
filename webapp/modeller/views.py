import os
import re
import subprocess
import uuid
import json

from . import modeller

from flask import g, current_app, render_template, request, jsonify, make_response, render_template, abort, redirect, url_for
from datetime import datetime, timedelta

from ..models import *

@modeller.route('/<model_name>')
def show_modeller(model_name):
    m = Model.query.filter(Model.name==model_name).first_or_404()
    if not m.validated:
        flash("Model '%s' has not been validated and cannot be run in the modeller."%(m.name),"error")
        return redirect(url_for('site.home'))
    if m.disabled:
        flash("Model has been deleted.")
        return redirect(url_for('site.home'))
        
    return render_template('modeller/modeller.html', model=m, discretization=m.discretization, u=current_user)

