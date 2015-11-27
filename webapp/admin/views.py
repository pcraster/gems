import os
import re
import subprocess
import uuid
import json
import glob 
import StringIO
import tempfile

from osgeo import ogr,osr
from owslib.wcs import WebCoverageService

from . import admin

from flask import g, current_app, render_template, request, jsonify, make_response, flash, url_for, redirect
from flask.ext.user import login_required, roles_required
from datetime import datetime, timedelta

from ..models import *

@admin.route('/')
@roles_required('admin')
def home():
    return 'Hello, admin blueprint!'

@admin.route('/datasets')
@roles_required('admin')
def datasets():
    """
    Shows information on datasets
    """
    wcss=[]
    for descr,url in current_app.config.get('WCS',{}).items():
        layers=[]
        wcs = WebCoverageService(url, version='1.0.0')
        for lyr in list(wcs.contents):
            layers.append({'name':lyr,'data':wcs.contents[lyr]})
            print dir(wcs.contents[lyr])
        wcss.append({'url':url,'layers':layers})
    return render_template("admin/datasets.html",wcs=wcss)
    
@admin.route('/users', methods=["GET"])
@roles_required('admin')
def users():
    """
    Show user list with options to add admins.
    """
    users=User.query.order_by(User.id).all()
    return render_template("admin/users.html",users=users)

@admin.route('/users/<int:uid>/<string:role>/toggle', methods=["GET"])
@roles_required('admin')
def users_make_admin(uid,role):
    """
    Show user list with options to add admins.
    """
    user = User.query.get(uid)
    if user.username != 'admin':
        user.toggle_role(role)
    return redirect(url_for('admin.users'))
    
@admin.route('/users/<int:uid>/reset-api-token')
@roles_required('admin')
def users_reset_api_token(uid):
    user = User.query.get(uid)
    user.reset_api_token()
    return redirect(url_for('admin.users'))

@admin.route('/users/<int:uid>/reset-password')
@roles_required('admin')
def users_reset_password(uid):
    user = User.query.get(uid)
    new_password = user.reset_password()
    flash("New password for user <code>%s</code> is <code>%s</code>. Please write it down, this is the only time that it is shown."%(user.username,new_password),"ok")
    return redirect(url_for('admin.users'))

@admin.route('/discretization',methods=["GET","POST"])
@roles_required('admin')
def discretization():
    """
    Shows information on domain discretization
    """
    if request.method=="POST":
        #try:
        if True:
            f = request.files['shapefile']
            temp = tempfile.NamedTemporaryFile(prefix='de-', suffix='.zip')
            f.save(temp.name)
            ds = ogr.Open("/vsizip/"+temp.name)
            if ds is not None:
                d = Discretization(request.form.get('name',''), ds, int(request.form.get('cellsize',100)))
                db.session.add(d) 
                db.session.commit()
                flash("New discretization was created!","ok")
            else:
                raise Exception("Temporary file '%s' could not be opened."%(temp.name))
        #except Exception as e:
        #    db.session.rollback()
        #    flash("An exception occurred while trying to add the discretization! Hint: %s"%(e),"error")
        #finally:
            ds = None
            temp.close()
        return redirect(url_for('admin.discretization'))
    else:
        return render_template("admin/discretization.html",discretizations=Discretization.query.all())

@admin.route('/processing')
@roles_required('admin')
def processing():
    """
    Shows information on processing
    """
    jobs=Job.query.order_by(Job.date_created.desc()).limit(10)
    return render_template("admin/processing.html",jobs=jobs)

@admin.route('/models/<model_name>/editor',methods=["GET","POST"])
def model_editor(model_name):
    """
    show the code editor
    """
    model=Model.query.filter_by(name=model_name).first_or_404()
    return render_template('admin/modeleditor.html',model=model)
    
@admin.route('/models/<model_name>/toggle-pin',methods=["GET"])
@roles_required('admin')
def model_toggle_pin(model_name):
    model = Model.query.filter_by(name=model_name).first_or_404()
    model.toggle_pin()
    return redirect(url_for('site.home'))
    
@admin.route('/models/<model_name>/toggle-disable',methods=["GET"])
@roles_required('admin')
def model_toggle_disable(model_name):
    model = Model.query.filter_by(name=model_name).first_or_404()
    model.toggle_disable()
    return redirect(url_for('site.home'))

@admin.route('/models/<model_name>/parameters',methods=["GET","POST"])
def model_parameters(model_name):
    """
    show the code editor
    """
    model=Model.query.filter_by(name=model_name).first_or_404()
    return render_template('admin/modelparameters.html',model=model)        

@admin.route('/models',methods=["GET","POST"])
@roles_required('admin')
def models():
    """
    Shows information on models
    """
    if request.method=="POST":
        name=re.sub(r'\W+',' ',request.form.get("modelname","")).lower()
        name="_".join(map(str,name.split()))
        
        if name == "":
            flash("Invalid model name.")
            return redirect(url_for('site.home'))
        
        model = Model.query.filter_by(name=name).first()
        if model is not None:
            flash("It seems like that model exists already! Please try another name.","error")
            return redirect(url_for('site.home'))
        
        try:
            model = Model(name=name)
            db.session.add(model)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("Something unexpected went wrong trying to add the model. Hint: %s"%(e),"error")
            return redirect(url_for('site.home'))
        else:
            return redirect(url_for('admin.model_editor',model_name=name))
    else:
        flash("Nothing here anymore.")
        return redirect(url_for('site.home'))
        
