import os
import re
import subprocess
import uuid
import json

from . import site

from flask import g, current_app, render_template, request, jsonify, make_response, redirect, url_for
from flask.ext.user import login_required, roles_required
from datetime import datetime, timedelta

from ..models import *


@site.route('/')
def home():
    if current_user.is_anonymous():
        return redirect(url_for('user.login'))
    else:
        stats=beanstalk.stats()
        return render_template("site/home.html",models=Model.query.all(),stats=stats)

@site.route('/models')
def models():
    return render_template("site/models.html",models=Model.query.all())
 
@site.route('/features')
def features():
    return render_template("site/features.html")
 
@site.route('/about')
def about():
    return render_template("site/about.html")
 
@site.route('/datasources')
def datasources():
    return render_template("site/datasources.html")