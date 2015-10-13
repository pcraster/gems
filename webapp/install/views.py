import os
import re
import subprocess
import uuid
import json
import inspect
import shutil
import requests
import itertools
import time
from . import install

from flask import g, current_app, render_template, request, jsonify, make_response, flash, stream_with_context, Response, redirect
from datetime import datetime, timedelta

from ..models import *




install_log = "";

@install.route('/')
def install_start():
    """
    This is the install view.
    """
    already_installed = os.path.exists(os.path.join(current_app.config["HOME"],"install","install-ok.txt"))
    return render_template("install/install.html", config=current_app.config, already_installed=already_installed)
            

@install.route('/eventstream')
def install_eventstream():
    if request.headers.get('accept') == 'text/event-stream':
        return Response(stream_with_context(install_application()), content_type='text/event-stream')
    else:
        return Response(stream_with_context(install_application()), content_type='text/plain')

def install_application():
    """
    Do the install...
    """
    yield "retry: 3600000\n\n"
    
    install_running_file = os.path.join("/tmp/","install-running.txt")
    install_ok_file = os.path.join(current_app.config["HOME"],"install","install-ok.txt")
    
    if os.path.exists(install_running_file):
        yield report("Another install is still running, please wait for that one to finish.",'error')
    elif os.path.exists(install_ok_file):
        yield report("GEMS application is already installed. Remove the install file before trying again.",'error')
    else:
        open(install_running_file, 'w')
        installation_steps = ('check_configuration','init_database','create_users','create_discretizations','create_models')
        try:
            for step in installation_steps:
                try:
                    yield report("Step '%s' started."%(step))
                    for message in globals()[step]():
                        yield message
                except Exception as e:
                    yield report("Step '%s' failed! (%s)"%(step,e),'error')
        except Exception as e:
            yield report("Installation failed! (%s)"%(e),'error')
        finally:
            os.remove(install_running_file)
            yield report("Installation completed! Head over to the <a href='/'>home page</a> to log in.")
            open(install_ok_file,'w')

def check_configuration():

    if os.path.isdir(current_app.config["HOME"]):
        yield report("HOME directory <code>%s</code> exists."%(current_app.config["HOME"]))
    else:
        yield report("HOME directory <code>%s</code> does not exist!"%(current_app.config["CODE"]),'error')
        raise Exception()
    
    if os.path.isdir(current_app.config["CODE"]):
        yield report("CODE directory <code>%s</code> exists."%(current_app.config["CODE"]))
    else:
        yield report("CODE directory <code>%s</code> does not exist!"%(current_app.config["CODE"]),'error')
        raise Exception()
    
    ###
    ### check that the data directory is writable
    ###
    try:
        tempdir = os.path.join(current_app.config["HOME"],"test-dir")
        tempfile = os.path.join(tempdir,"test-writable.txt")
        shutil.rmtree(tempdir,ignore_errors=True)
        os.makedirs(tempdir)
        f = open(tempfile, 'w')
        f.close()
        os.remove(tempfile)
        shutil.rmtree(tempdir)
        yield report("HOME directory <code>%s</code> is writable."%(current_app.config["HOME"]))
    except Exception as e:
        yield report("HOME directory <code>%s</code> is NOT writable! Can't create files or directories. (%s)"%(current_app.config["HOME"], e),'error')
        
    ###
    ### delete all the files in the data directory
    ###
    try:
        for file_object in os.listdir(current_app.config["HOME"]):
            file_object_path = os.path.join(current_app.config["HOME"], file_object)
            if os.path.isfile(file_object_path):
                os.unlink(file_object_path)
            else:
                shutil.rmtree(file_object_path)
        yield report("Deleted all files and subdirectories of <code>%s</code>"%(current_app.config["HOME"]))
    except Exception as e:
        yield report("Could not delete all files and subdirectories of <code>%s</code>. (%s)"%(current_app.config["HOME"],e),'error')
        
    ###
    ###  create subdirectories
    ###
    try:
        subdirectories_list = ('incoming_maps','install','maps','mapserver_templates','models','tilecache','tmp')
        for subdirectory in subdirectories_list:
            os.makedirs(os.path.join(current_app.config["HOME"],subdirectory))
        yield report("Created subdirectories <code>%s</code> in HOME directory <code>%s</code>"%("</code>, <code>".join(subdirectories_list),current_app.config["HOME"]))
    except Exception as e:
        yield report("Could not create subdirectories. (%s)"%(e),'error')
        

    ###
    ### check the data directory is writable
    ###
    tempdir = current_app.config["TEMP"]
    if not os.path.isdir(tempdir):
        try:
            os.makedirs(tempdir)
            yield report("TEMP directory <code>%s</code> does not exist. Created it successfully."%(tempdir))
        except Exception as e:
            yield report("TEMP directory <code>%s</code> does not exist. Creating it failed! (%s)"%(tempdir,e),'error')
    else:
        yield report("TEMP directory found at <code>%s</code."%(tempdir))
            
    ###
    ### check the data directory is writable
    ###
    try:
        tempfile = os.path.join(current_app.config["TEMP"],"test-writable.txt")
        f = open(tempfile, 'w')
        f.close()
        os.remove(tempfile)
        yield report("TEMP directory <code>%s</code> is writable."%(current_app.config["TEMP"]))
    except IOError:
        yield report("TEMP directory <code>%s</code> is NOT writable!"%(current_app.config["TEMP"]),'error')
        
    ###
    ### check the data directory is writable
    ###
    try:
        beanstalk.stats()
        yield report("Connected to beanstalk work queue!")
    except Exception as e:
        yield report("Could not connect to beanstalkd work queue. Make sure the service is running and that it is accessible from this machine.",'error')
    
    ###
    ### check that mapserver instance at MAPSERVER_URL returns something sensible
    ###
    r = requests.get(current_app.config["MAPSERVER_URL"])
    if (r.status_code == 200) and ("QUERY_STRING is set, but empty." in r.text):
        yield report("Mapserver found at <code>%s</code>"%(current_app.config["MAPSERVER_URL"]))
    else:
        yield report("Mapserver not found at <code>%s</code>"%(current_app.config["MAPSERVER_URL"]),'error')
        
    yield report("Completed!")
    
def init_database():
    try:
        db.drop_all()
        yield report("Dropped database")
    except Exception as e:
        yield report("Dropping database failed! (%s)"%(e),'error')
    try:
        db.create_all()
        yield report("Created database tables")
    except Exception as e:
        yield report("Creating database tables failed. (%s)"%(e),'error')
    yield report("Completed!")
    
def create_users():
    try:
        db.session.add(Role(name="admin"))
        db.session.commit()
        users = []
        admin_password = random_password()
        admin = User(username='admin', fullname='Site Administrator', email='', active=True, password=current_app.user_manager.hash_password(admin_password))
        admin.roles.append(Role.query.filter(Role.name=='admin').first())
        users.append(admin)
        db.session.add_all(users)
        db.session.commit()
        yield report("<strong>Created default user <code>admin</code>. Password for admin is <code>%s</code>, write this down somewhere safe, this is the only time that the new admin password is shown!</strong>"%(admin_password))
    except Exception as e:
        yield report("Exception occurred while creating default users. (%s)"%(e),'error')
    yield report("Completed!")

def create_discretizations():
    """
    Initializes the database with default users, chunkschemes, and models.
    """
    yield report("Creating <code>newzealand_onedegree</code>")
    yield create_discretization("newzealand_onedegree")
    
    yield report("Creating <code>frankrijk_veldwerkgebied</code>")
    yield create_discretization("frankrijk_veldwerkgebied")
    
    yield report("Creating <code>thames</code>")    
    yield create_discretization("thames")
    
    yield report("Creating <code>world_onedegree</code> (this one is rather large so it may take a while, please be patient...)")
    yield create_discretization("world_onedegree")
    
def create_models():
    """
    Initializes the default models.
    """
    yield report("Load model <code>example</code>")
    yield create_model("example")
    yield report("Load model <code>pcrtopo</code>")
    yield create_model("pcrtopo")
    yield report("Load model <code>forecast</code>")
    yield create_model("forecast")
    yield report("Load model <code>globerosion</code>")
    yield create_model("globerosion")

#    create_discretization("european_catchments")
#    create_discretization("newzealand_subcatchments")
#    create_discretization("newzealand_randompolygons")

def create_discretization(name):
    """
    Creates a discretization in the database from a zipfile containing 
    polygon features. New disretizations are created by uploading a shapefile
    in the admin interface. This bit of code is used when initializing the
    app from scratch.
    
    Todo:
    - implement a cell size parameter
    """
    try:
        filename = os.path.join(current_app.config["CODE"],"data","discretizations",name+".zip")
        ds = ogr.Open("/vsizip/"+filename)
        if ds is not None:
            db.session.add(Discretization(name, ds, 100))
            db.session.commit()
        else:
            raise Exception("No data found in: %s"%(filename))
    except Exception as e:
        db.session.rollback()
        return report("Creating discretization <code>%s</code> failed! (%s)"%(name,e),'error')
    else:
        return report("Created discretization <code>%s</code>."%(name))
    finally:
        ds = None

def create_model(name):
    """
    Creates a new model.
    """
    try:
        filename = os.path.join(current_app.config["CODE"],"data","models",name,name+".py")
        with open(filename) as f:
            print "Creating model '%s'..."%(name)
            db.session.add(Model(name=name,code=f.read()))
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        return report("Loading model <code>%s</code> failed! (%s)"%(name,e),'error')
    else:
        return report("Loaded model <code>%s</code>."%(name))
    finally:
        pass

def random_password():
    return ''.join(random.choice("abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        
def report(message, category='ok'):
    source = inspect.getouterframes(inspect.currentframe())[1]
    if category != 'error':
        return "data: <tr><td><nobr><i class='fa fa-fw fa-check'></i> %s</nobr></td><td>%s</td></tr>\n\n"%(source[3],message)
    else:
        return "data: <tr><td><nobr><strong><i class='fa fa-fw fa-exclamation-circle'></i> %s</strong></nobr></td><td>%s</td></tr>\n\n"%(source[3],message)