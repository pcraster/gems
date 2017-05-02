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
        #The highlighted models which are available to all users
        jobs = Job.query.order_by(Job.date_created.desc()).filter(Job.user==current_user, Job.status_code==1).limit(5)
        models = Model.query.order_by(Model.name).filter(Model.highlighted==True, Model.disabled==False).all()
        
        #The other (test) models which are not on the homepage.
        other_models = Model.query.order_by(Model.disabled, Model.name).filter(Model.highlighted==False).all()
        return render_template("site/home.html", models=models, other_models=other_models, jobs=jobs)
        
@site.route('/myaccount')
@login_required
def myaccount():
    return render_template("site/myaccount.html")
    
@site.route('/myaccount/reset-api-token')
@login_required
def myaccount_reset_api_token():
    current_user.reset_api_token()
    return redirect(url_for('site.home'))
    

@site.route('/models')
def models():
    return render_template("site/models.html", models=Model.query.all())
 
@site.route('/features')
def features():
    return render_template("site/features.html")
 
@site.route('/about')
def about():
    return render_template("site/about.html")
 
@site.route('/datasources')
def datasources():
    return render_template("site/datasources.html")