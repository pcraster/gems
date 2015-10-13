#!/usr/bin/env python
from flask.ext.script import Manager, Shell, Server
from webapp import *
#from osgeo import gdal, gdalconst, ogr, osr

manager = Manager(app)

manager.add_command("runserver", Server())
manager.add_command("shell", Shell())

@manager.command
def createdb():
    """
    Create the database.
    """
    db.create_all()

@manager.command
def dropdb():
    """
    Drop the database. Use with care!
    """
    db.drop_all()

@manager.command
def purgedb():
    """
    Drop and create the database. Use with care!
    """
    dropdb()
    createdb()
    createusers()
    initdb()
    
@manager.command
def initdb():
    """
    Initializes the database with default users, chunkschemes, and models.
    """
    creatediscretizations()

@manager.command
def createdirectories():
    """
    Initializes the directory structure in the data directory.
    """
    pass

@manager.command
def creatediscretizations():
    """
    Initializes the database with default users, chunkschemes, and models.
    """
    creatediscretization("world_onedegree")
    creatediscretization("newzealand_onedegree")
    creatediscretization("frankrijk_veldwerkgebied")
    creatediscretization("newzealand_subcatchments")
    creatediscretization("newzealand_randompolygons")
    creatediscretization("european_catchments")
    creatediscretization("thames")
    
@manager.command
def createmodels():
    createmodel("example")
    createmodel("pcrtopo")
    createmodel("forecast")
    createmodel("globerosion")

@manager.command
def resetpassword():
    """
    Reset password
    """
    pass

@manager.command
def checkrequirements():
    """
    Checks the requirements.
    
    Todo:
        - check the required modules
        - make sure mapserver can be found
        - make sure pcraster can be found and imported
    """
    pass

@manager.command
def install():
    """
    Installs the application.
    - Delete everything
    - Create default user accounts
    - Create the default discretization scheme
    - Upload several test models
    """
    pass

@manager.command
def creatediscretization(name):
    """
    Creates a discretization in the database from a zipfile containing 
    polygon features. New disretizations are created by uploading a shapefile
    in the admin interface. This bit of code is used when initializing the
    app from scratch.
    
    Todo:
    - implement a cell size parameter
    """
    try:
        filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),"data","discretizations",name+".zip")
        ds = ogr.Open("/vsizip/"+filename)
        if ds is not None:
            print "Creating discretization '%s'..."%(name)
            db.session.add(Discretization(name, ds, 100))
            db.session.commit()
            print "Ok!"
        else:
            print "No data found in: %s"%(filename)
    except Exception as e:
        db.session.rollback()
        print "Failed! Hint: %s"%(e)
    else:
        print "Discretization created successfully!"
    finally:
        ds = None

@manager.command
def createmodel(name):
    """
    Creates a new model.
    """
    try:
        filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),"data","models",name,name+".py")
        with open(filename) as f:
            print "Creating model '%s'..."%(name)
            db.session.add(Model(name=name,code=f.read()))
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print "Failed! Hint: %s"%(e)
    else:
        print "Model created successfully!"
    finally:
        pass

@manager.command
def createuser(name):
    """
    Creates a new user
    """
    pass

@manager.command
def createusers():
    db.session.add(Role(name="admin"))
    db.session.commit()
    
    pw_admin=random_password()    
    admin = User(username='admin', fullname='Site Administrator', email='k.alberti@uu.nl', active=True, password=user_manager.hash_password('admin'))
    admin.roles.append(Role.query.filter(Role.name=='admin').first())
    demo = User(username='demo', fullname='Demo user', email='k.alberti@students.uu.nl', active=True, password=user_manager.hash_password('demo'))

    db.session.add_all([admin,demo])
    db.session.commit()

    print "Credentials: admin/%s and demo/demo"%(pw_admin)

def random_password():
    return ''.join(random.choice("abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))

if __name__=="__main__":
    manager.run()