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
from datetime import datetime, timedelta

from ..models import *

@admin.route('/')
def home():
    return 'Hello, admin blueprint!'

@admin.route('/datasets')
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

@admin.route('/discretization',methods=["GET","POST"])
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
def processing():
    """
    Shows information on processing
    """
    jobs=Job.query.order_by(Job.date_created.desc()).limit(10)
    stats=beanstalk.stats()
    return render_template("admin/processing.html",jobs=jobs,stats=stats)

@admin.route('/models/<model_name>/editor',methods=["GET","POST"])
def model_editor(model_name):
    """
    show the code editor
    """
    model=Model.query.filter_by(name=model_name).first_or_404()
    return render_template('admin/modeleditor.html',model=model)

@admin.route('/models/<model_name>/parameters',methods=["GET","POST"])
def model_parameters(model_name):
    """
    show the code editor
    """
    model=Model.query.filter_by(name=model_name).first_or_404()
    return render_template('admin/modelparameters.html',model=model)        

@admin.route('/models',methods=["GET","POST"])
def models():
    """
    Shows information on models
    """
    if request.method=="POST":
        try:
            f = request.files['modelfile']
            _modelcode=""
            if f:
                _modelcode=f.read()
            
            model=Model.query.filter_by(name=request.form.get("modelname","")).first()
            if model==None:
                model=Model(name=request.form.get("modelname",""),code=_modelcode)
                db.session.add(model)
                db.session.commit()
                flash("Created a new model <code>%s</code>"%(model.name),"ok")
            else:
                model.updatecode(_modelcode)
                db.session.commit()
                flash("Model already existsed! Updated code and increased version.")
        except Exception as e:
            flash("Something went wrong creating/updating your model. Hint: %s"%(e),"error")
        return redirect(url_for('admin.models'))
    return render_template("admin/models.html",models=Model.query.all())

@admin.route('/configuration')
def configuration():
    """
    Shows information on the site configuration
    """
    for module in current_app.config["MODULES"]:
        try: 
            __import__(module)
            flash("Imported module <code>%s</code>."%(module),"ok")
        except Exception as e:
            flash("Could not import module <code>%s</code>. Hint: %s"%(module,e),"error")

    for key, value in current_app.config["UTILS"].iteritems():
        if os.path.isfile(value) and os.access(value, os.X_OK):
            flash("Utility program <code>%s</code> found and is executable."%(value),"ok")
        else:
            flash("Utility program <code>%s</code> was not found or is not executable!"%(value),"error")
    return render_template("admin/configuration.html")