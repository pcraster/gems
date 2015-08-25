import os
import uuid
import pyproj
import mercantile
import subprocess
import hashlib
import base64
import StringIO
import random
import re
import sys
import beanstalkc 
import json
import utm
import cPickle
import datetime

import numpy as np
import numpy.ma as ma
import matplotlib.cm as mpcm

from osgeo import gdal, gdalconst, ogr, osr

from functools import partial

from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.user import UserManager, UserMixin, SQLAlchemyAdapter
from flask.ext.user import current_user, login_required, roles_required, UserMixin

#from flask.ext.login import UserMixin, AnonymousUserMixin
from flask import render_template, current_app, flash

from werkzeug.security import generate_password_hash, check_password_hash

from geoalchemy2 import Geometry
from geoalchemy2.shape import to_shape,from_shape
from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_Envelope, ST_AsText, ST_AsGeoJSON, ST_Distance, ST_Centroid

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import UUID, JSON

from shapely.ops import transform, cascaded_union
from shapely.geometry import box, mapping, Polygon, Point, MultiPolygon
from shapely.wkt import loads

from utils import create_configuration_key, parse_model_time

db = SQLAlchemy()

beanstalk = beanstalkc.Connection(host='localhost',port=11300)


class Discretization(db.Model):
    """
    Describes the discretization used to divide the earth up into managable
    chunks which can be processed individually. Once created, discretizations 
    cannot be modified or deleted.

    Todo: * Add a coverage field, which is a single multipolygon  or a centroid
            or something to navigate to per default.
          * Default location (see above) also for discretizations with only 
          one chunk. Will allow for running a model only in one location.

    """
    __tablename__='discretization'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(512), unique=True, nullable=False, index=True)
    description = db.Column(db.String(1024), unique=False, nullable=True, index=False)
    cellsize = db.Column(db.Integer(), nullable=False, default=100)
    num_of_chunks = db.Column(db.Integer(), nullable=False)
    buffer_ = db.Column(db.Integer(), nullable=False, default=1000)
    coverage = db.Column(Geometry(geometry_type='MULTIPOLYGON', srid=4326))
    extent = db.Column(Geometry(geometry_type='POLYGON', srid=4326))

    def __repr__(self):
        return "<Discretization: %s>"%(self.name)

    def __init__(self, name="", dataset=None, cellsize=100):
        """
        Create a new discretization. The following arguments are required:
        
        - dataset (a gdal vector dataset. all the polygons will be extracted and used)
        - cell size (integer in meters)
        - name
        
        Todo:
        Look into other ways of simplifying the coverage. If a large shapefile with
        very detailed polygons is uploaded it creates a lot of overhead. We solve this
        now by creating the coverage by doing a cascaded union on the envelopes of 
        all the individual polygons. This saves a lot of processing, and while the 
        results are a bit more ugly than neatly unioned polygons with real catchment
        shapes, it doesnt make much difference in the end when the coverage is just used
        for showing where the model can be run, and setting the map to this location
        automatically if no other place was specified.
        
        """
        if dataset is None:
            raise Exception("Dataset with features cannot be accessed.")
            
        layer = dataset.GetLayer(0)
        srs = layer.GetSpatialRef()
        srs.AutoIdentifyEPSG()
        srs_authority_code = srs.GetAuthorityCode(None)
        layer_epsg = None
        
        if srs_authority_code is None:
            raise Exception("Could not get epsg code of the shapefile using srs.GetAuthorityCode")
            
        try:
            layer_epsg = int(srs.GetAuthorityCode(None))
        except:
            layer_epsg = None
            
        polygons = []

        if layer_epsg != 4326:
            raise Exception("Shapes must be in WGS84 latlng coordinates (epsg 4326)")
        else:
            feature = layer.GetNextFeature()
            while feature:
                if feature:
                    try:
                        geom = feature.GetGeometryRef()
                        if geom.GetGeometryName() == "POLYGON":
                            polygons.append(geom.ExportToWkt())
                    except Exception as e:
                        print "Skipping a feature: %s"%(e)
                feature = layer.GetNextFeature()

        self.cellsize = cellsize
        
        name = re.sub(r'\W+',' ',name).lower()
        name = "_".join(map(str,name.split()))
        if name == "":
            name = "unnamed_"+hashlib.md5(str(random.random())).hexdigest()[0:6]+"_%dm"%(self.cellsize)
        else:
            name = name+"_%dm"%(self.cellsize)
        self.name = name
        
        num_of_chunks = 0
        for polygon in polygons:
            self.chunks.append(Chunk(wkt_polygon=polygon))
            num_of_chunks+=1
            
        print "Found %d polygon features."%(num_of_chunks)
        self.num_of_chunks=num_of_chunks
            
        print "Creating cascaded union... This may take a while if your polygons are complicated..."
        chunk_polygons = MultiPolygon(polygons=[loads(wkt).buffer(0.01) for wkt in polygons])
        
        chunk_extents = MultiPolygon(polygons=[box(*loads(wkt).buffer(0.01).bounds) for wkt in polygons])
        
        chunk_union = cascaded_union(chunk_extents)

        print "Simplifying the merged polygon further since this one is only used for display purposes."
        chunk_union.simplify(0.01)
        
        if chunk_union.geom_type == 'Polygon':
            # If all the chunks were connected to each other then a Polygon is
            # is created rather than a MultiPolygon. Our database column needs
            # a MultiPolygon, so convert it before saving it.
            chunk_union = MultiPolygon([chunk_union])
        print "Done!"
        chunk_box = box(*chunk_union.bounds)

        self.coverage = from_shape(chunk_union, srid=4326)
        self.extent = from_shape(chunk_box, srid=4326)
        print "Storing..."
        
    @property
    def extent_as_bounds(self):
        bounds = to_shape(self.extent).bounds
        return ",".join(map(str,bounds))
        #return db.session.scalar(ST_AsGeoJSON(self.extent))
        
    @property
    def coverage_as_geojson(self):
        cov = to_shape(self.coverage)
        return json.dumps(mapping(cov))
        
class Chunk(db.Model):
    """
    Describes a unit within a discretization. For example, the discretization
    "world_onedegree" divides the world into ~50000 chunks of 1x1 degree. This
    model describes those individual chunks. The chunks are assigned to 
    processing requests and processed individually.
          
    """
    __tablename__='chunk'
    id = db.Column(db.Integer(), primary_key=True)
    discretization_id = db.Column(db.Integer(), db.ForeignKey('discretization.id'))
    discretization = db.relationship('Discretization', backref=db.backref('chunks', lazy='dynamic'))
    jobchunks = db.relationship('JobChunk', backref='chunk', lazy='dynamic')
    uuid = db.Column(UUID, index=True)
    geom = db.Column(Geometry(geometry_type='POLYGON', srid=4326))
    
    def __init__(self,wkt_polygon):
        self.uuid=str(uuid.uuid4())
        self.geom=from_shape(loads(wkt_polygon),srid=4326)
        
    @property
    def as_grid(self):
        geom=to_shape(self.geom)
        return {
            'bounds':geom.bounds,
            'bbox':self.bbox,
            'uuid':str(self.uuid),
            'discretization':self.discretization.name,
            'cellsize':self.discretization.cellsize,
            'srid':self.srid
        }
    @property
    def grid(self):
        """
        Returns a grid representation of this chunk, including the bounding box,
        geotransform variables, cellsize, rows, cols, etc. All this information
        is used to construct a grid and a mask on which the model will be run
        in the end.
        """
        geom=to_shape(self.geom)
        return {
            'bounds':geom.bounds,
            'bbox':self.bbox,
            'geotransform':self.geotransform,
            'uuid':str(self.uuid),
            'discretization':self.discretization.name,
            'cellsize':self.discretization.cellsize,
            'pixelheight':self.pixelheight,
            'pixelwidth':self.pixelwidth,
            'srid':self.srid,
            'rows':self.rows,
            'cols':self.cols,
            'projection':self.projection,
            'mask':self.mask.wkt
        }
    @property
    def srid(self):
        epsg=32600
        geom=to_shape(self.geom)
        (easting,northing,zone,zone_letter)=utm.from_latlon(geom.centroid.y, geom.centroid.x)
        if zone_letter<'N': #southern zones get +100
            epsg+=100
        return epsg+zone
        
    @property
    def cellsize(self):
        return 100
        
    @property
    def pixelwidth(self):
        (minx, miny, maxx, maxy) = self.bbox
        return (maxx-minx)/self.cols

    @property
    def pixelheight(self):
        (minx, miny, maxx, maxy) = self.bbox
        return (miny-maxy)/self.rows        
        
    @property
    def bbox(self):
        """
        Return the chunk bounds in a local utm projection
        
        Todo: cache this after generating it, because it's really inefficient
        calling rows or pixelheight properties now.
        
        (minx, miny, maxx, maxy)
        """
        project=partial(pyproj.transform, pyproj.Proj(init="epsg:4326"), pyproj.Proj(init="epsg:%d"%(self.srid)))
        return transform(project,to_shape(self.geom)).bounds
        
    @property
    def mask(self):
        """
        Return the chunk polygon in a local projection.
        """
        project=partial(pyproj.transform, pyproj.Proj(init="epsg:4326"), pyproj.Proj(init="epsg:%d"%(self.srid)))
        return transform(project,to_shape(self.geom))
        
    @property
    def rows(self):
        """
        Return the number of rows that this chunk has in the local utm
        projection.
        """
        bbox=self.bbox
        return int(round((bbox[3]-bbox[1])/self.cellsize))

    @property
    def cols(self):
        """
        Return the number of cols that this chunk has in the local utm
        projection.
        """
        bbox=self.bbox
        return int(round((bbox[2]-bbox[0])/self.cellsize))
        
    @property
    def projection(self):
        """
        Return a wkt projection string.
        """
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(self.srid) 
        return ref.ExportToWkt()
        
    @property
    def geotransform(self):
        """
        Returns the 6 coefficients which map pixel/line coords into a geo-
        referenced space. These coordinates are a function of self.bbox and
        self.cellsize and are assigned to output datasets using gdal's 
        SetGeoTransform function.
        
        The coefficients are (left,pixelwidth,0,top,0,pixelheight)
        
DEBUG Projection is: 
2015-06-25 17:44:51,848 DEBUG PROJCS["WGS 84 / UTM zone 60S",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",177],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",10000000],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AUTHORITY["EPSG","32760"]]
2015-06-25 17:44:51,848 DEBUG Geotransform is:
2015-06-25 17:44:51,849 DEBUG (414639.56133316015, 99.9536481158079, 0.0, 5572242.772899812, 0.0, -99.98327705229146)

        
        """
        (minx, miny, maxx, maxy) = self.bbox
        return (minx,self.pixelwidth,0,maxy,0,self.pixelheight)


class Map(db.Model):
    """
    Describes a single output map generated by a model. Maps created by models
    are identifiable by:
    
    - model configuration id (foreign key modelconfiguration.id)
    - chunk id (or geometry)
    - attribute name that was given when the map was reported
    - timestamp 
    
 
    
    Todo:
    - add timestamp field
    - add datatype field
    - add stats fields (min,max) for visualization purposes...
    - consider adding a "MapSet" model where the attribute properties
      are defined. Otherwise we'll just have to filter for uniques in this
      massive table and turn each unique attribute into a mapserver layer.
    """
    __tablename__='map'
    id = db.Column(db.Integer(), primary_key=True)

    #The model configuration that this map was generated with
    modelconfiguration_id = db.Column(db.Integer(), db.ForeignKey('modelconfiguration.id'))
    modelconfiguration = db.relationship('ModelConfiguration', backref='maps')
    
    #This config key is a duplicate of modelconfiguration.key and is added
    #here as a separate field because mapserver needs to be able to query this
    #table via postgis by config key, rather than just the id of the modelconfiguration.
    config_key = db.Column(db.String(32), nullable=False, unique=False, index=True)
    
    #Other important keys are the timestamp and attribute
    timestamp = db.Column(db.DateTime(),nullable=True, index=True)
    attribute = db.Column(db.String(1024), nullable=False, index=True)

    #Modified. Important for caching... if maps newer than the cahced tile 
    #exist, refetch from mapserver.
    #modified = db.Column(db.DateTime(),nullable=False, index=True, default=db.func.now())

    #The chunk that this map was created on. Steal the extent from the chunk
    #too. While this works nicely now, mapserver needs the geometry of a tile-
    #index to be a column of the actual table, not a reference to another 
    #table like the chunk table. So, add a geometry field to the map as well,
    #this is popuplated upon creation with a copy of the geom of the chunk.
    chunk_id = db.Column(db.Integer(), db.ForeignKey('chunk.id'))
    chunk = db.relationship('Chunk', backref='maps')
    
    geom = db.Column(Geometry(geometry_type='POLYGON', srid=4326))
    geom_web_mercator = db.Column(Geometry(geometry_type='POLYGON', srid=3857))
    
    datatype = db.Column(db.String(1024), nullable=False, index=False)    
    filename = db.Column(db.String(1024), nullable=False, index=False)

    def __repr__(self):
        return "<Map config=%s chunk=%s time=%s filename=%s>"%(self.config_key[0:6],self.chunk.uuid[0:6],self.timestamp.isoformat(),self.filename) 
        
    def __init__(self,chunk,modelconfiguration,options):
        self.chunk=chunk
        self.modelconfiguration=modelconfiguration
        self.config_key=modelconfiguration.key
        self.geom=chunk.geom
        
        project=partial(pyproj.transform, pyproj.Proj(init="epsg:4326"), pyproj.Proj(init="epsg:3857"))
        self.geom_web_mercator=from_shape(transform(project,to_shape(self.geom)),3857)        
        
        self.attribute=options["attribute"]
        self.filename=os.path.join(current_app.config["HOME"],"maps",options["filename"])
        self.datatype=options["datatype"]
        self.timestamp=datetime.datetime.strptime(options["timestamp"], "%Y%m%d%H%M%S")
    
class Model(db.Model):
    """
    Describes a pcraster-python model which can be run in this environment.

    Todo:
        - add owner
        - add 'public' boolean
        - add 'nocache' boolean
        - add last updated
        - use a getter and setter for the code attribute
        - use templates for generating mapserver config
        
        - clean up and refactor code

    """
    __tablename__='model'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(512), unique=True, nullable=False, index=True)
    
    abstract = db.Column(db.Text(), unique=False, nullable=True)
    contact = db.Column(db.String(512), unique=False, nullable=True)

    #jobs = db.relationship('Job', backref='model', lazy='dynamic')
    
    modified = db.Column(db.DateTime(),nullable=True)
    discretization_id = db.Column(db.Integer(), db.ForeignKey('discretization.id'))
    version = db.Column(db.Integer(),default=1)

    modelcode = db.Column(db.Text(), nullable=True, unique=False)

    meta = db.Column(JSON(), nullable=True)
    parameters = db.Column(JSON(), nullable=True)
    time = db.Column(JSON(), nullable=True)
    reporting = db.Column(JSON(), nullable=True)
    
    def __repr__(self):
        return "<Model: name=%s id=%d>"%(self.name,self.id)
        
    def __init__(self,name="",code=""):
        name=re.sub(r'\W+',' ',name).lower()
        name="_".join(map(str,name.split()))
        self.name=name
        self.version=1
        self.updatecode(code)        
        
    @property
    def as_dict(self):
        return {
            "meta":self.meta,
            "reporting":self.reporting,
            "time":self.time
        }
        
    @property
    def filename(self):
        return os.path.join(self.filedir,"modelcode.py")

    @property
    def filedir(self):
        _model_dir=os.path.join(current_app.config["HOME"],"models",self.name)
        if not os.path.isdir(_model_dir):
            os.makedirs(_model_dir)
        return os.path.join(_model_dir)
    @property
    def mapserver_config_params(self):
        """
        Returns a dict with configuration parameters that are needed for 
        configuring this model with mapserver.
        """
        return {
            "wms_timeextent":",".join(self.timestamp_list),
            "wms_timedefault":self.timestamp_list[-1]      
        }
        
    @property
    def timestamp_list(self):
        """
        Return a list of timestamps for each timestep in this model.
        
        Deprecated! A model no longer has a start time, as this is defined by
        the modelconfiguration!
        
        Todo: delete this
        
        """
        #epoch=datetime.datetime.strptime(self.time["start"],"%Y-%m-%dT%H:%M:%S")
        epoch=self.start
        timestamp_list=[]
        for timestep in range(self.time['timesteps']):
            seconds_to_add=(timestep)*self.time["timesteplength"]
            if seconds_to_add<0: #in case currentStep=0
                seconds_to_add=0
            timestamp=(epoch + datetime.timedelta(seconds=seconds_to_add))
            timestamp_list.append(timestamp.isoformat())
        return timestamp_list
        
    @property
    def start(self):
        """
        Return the start time of this model. Can either be fixed, or dynamic
        based on UTC time (for forecast models) using a rounding factor, and 
        a time offset. 
        """
        
        time_rounding = self.time.get("startroundoff", -60) #default to 60s
        time_offset = self.time.get("startoffset", 0) #default to 0
        
        return parse_model_time(self.time["start"],round_to=time_rounding,offset=time_offset)

    def updateversion(self):
        self.modified=db.func.now()
        if self.version==None:
            self.version=1
        else:
            self.version=self.version+1

    def updatecode(self,code):
        #
        # Todo:
        # save the code to a temporary directory where we can try and load it.
        # if that succeeds, do the rest of the handling and copy it to the main
        # directory. this way the code is only overwritten if it loads properly
        # and does not produce any parsing errors. currently the code is saved
        # to file first, then if there are any errors they persist in the file,
        # which is not what we want to have happen.
        #
    
        print "Removing old code:"
        c=["/bin/rm",os.path.join(self.filedir,"modelcode.py")]
        print " ".join(c)     
        subprocess.call(c)

        c=["/bin/rm",os.path.join(self.filedir,"modelcode.pyc")]
        print " ".join(c)     
        subprocess.call(c)


        print " * Update code, writing to: %s"%(self.filename)
        #subprocess.call("/bin/rm",)
        with open(self.filename,'w') as f:
            f.write(code)
        

        sys.path.append(self.filedir)
        
        code_path = os.path.join(current_app.config["CODE"],"processing")
        
        sys.path.append(code_path)
        
        module=__import__("modelcode")
        model=getattr(module,"Model")

        m=model()
        
        print "meta:"
        print m.meta
        print "params:"
        print m.parameters
        
        self.parameters=m.parameters
        self.time=m.time
        self.meta=m.meta
        self.reporting=m.reporting
        
                
        
        db.session.commit()
        print " * Update version"
        self.updateversion()
        self.update_mapserver_template()
        print " * saving templates"
        db.session.commit()
        
        print " *unloading model"
        del module
        del sys.modules["modelcode"]
        del m
        sys.path.remove(self.filedir)
        sys.path.remove(code_path)
        
    def update_mapserver_template(self):
        """
        Updates the mapserver .map file for the outputs created by this model.
        
        """
        with open(self.mapserver_mapfile,'w') as f:
            mapserver_template=render_template('mapserver/page.map',model=self)
            f.write(mapserver_template)
        return True
        
    def configure(self,parameters={}):
        """
        Configure a model with the parameters passed in the 'parameters' dict.
        This will return a ModelConfiguration instance. Only items in the 
        paramters dict will be included which have a matching entry in the 
        model's parameters section.
        
        There are several 'special' variables which are included/embedded 
        automatically model run configuration but which are not directly 
        configurable by the user. These are used for internal purposes and so
        that the config key will change when the model uses a different start
        time, is run on a different discretization with otherwise the same
        user provided parameters. These special parameters are:
        
        __start__               The start time of the model. This may be unique 
                                to the model run if we're using a forecast
                                which always starts 'now', meaning no results
                                can be cached.
        
        __discretization__      The discretiztion we're doing this model run
                                on. This determines the geographic extent of 
                                the run as well as the cellsize.
        
        __model__               The name of the model
        
        __version__             The version of the model. Obviously when a user
                                edits model code this version will change, 
                                resulting in a new config key being generated 
                                for the next run - even if all the other p
                                parameters remain the same.
        
        These inputs are ignored by the web interface, so they won't be shown
        as input boxes there.
        """
        modelparams=self.parameters
        
        #set the model parameters
        for k,v in parameters.items():
            if k in modelparams:
                #if one of the parameters matches one defined in the 
                #parameters section of the model, try to convert it to the 
                #same data type as the one in the parameters section. 
                paramtype=type(modelparams[k])
                if paramtype is int:
                    try: v=int(v)
                    except: pass
                if paramtype is float:
                    try: v=float(v)
                    except: pass
                modelparams.update({k:v})

        #add the default parameters to the configuration as well
        modelparams.update({
            '__start__':            self.start.isoformat(),
            '__timesteps__':        self.time['timesteps'],
            '__discretization__':   "european_catchments_100m",
            '__model__':            self.name,
            '__version__':          self.version
        })

        #create a configuration with a configuration id for this job
        config_key,config_string,parameters=create_configuration_key(modelparams)
        print "Key '%s' consists of:"%(config_key)
        print parameters

        modelconfiguration=ModelConfiguration.query.filter(ModelConfiguration.key==config_key).first()
        
        if modelconfiguration is None:
            #apparently this model configuration because the set of params
            #has not been used before. therefore we create a new modelconfiguration
            #in the database and return the new one instead, because we must
            #always return a valid config when running configure() on a model.
            modelconfiguration=ModelConfiguration(config_key,config_string,self,modelparams)
            
        db.session.commit()
        return modelconfiguration
    
    @property
    def mapserver_mapfile(self):
        """
        Returns the filename of the mapserver configuration file for this model.
        This file defines how all the output layers will look.
        """
        _dir=os.path.join(current_app.config["HOME"],"mapserver_templates")
        if not os.path.isdir(_dir):
            os.makedirs(_dir)
        return os.path.join(_dir,self.name+".map")
    
    @property
    def code(self):
        """
        Returns the model code of this model.
        """
        with open(self.filename) as f:
            return f.read()
    
    @property
    def default_config_key(self):
        """
        Returns a configuration key for this model with the default parameters.
        """
        modelconfig=self.configure()
        return modelconfig.key
        
        
    @property
    def preferred_discretization_name(self):
        try:
            discretization_name = self.meta.get('discretizations')[0]
        except:
            discretization_name = "world_onedegree_100m"
        return discretization_name

    @property
    def parameters_as_pretty_json(self):
        return json.dumps(self.parameters, sort_keys=True, indent=4)
        
    @property
    def parameters_as_json_schema(self):
        import genson
        s = genson.Schema()
        s.add_object(self.parameters)
        return json.dumps(s.to_dict(), sort_keys=True, indent=4)
    
    @property
    def default_modeller_hash(self):
        """
        Returns a default hash for the modeller part of the web application.
        The default hash is used in presetting the configuration key to run
        the model with, the zoom level, and the location of the model. This 
        is configure here because later we might want to change the default
        location depending on the model.
        """
        return "%s,%.6f,%.6f,%d"%(self.default_config_key,-40.6139,176.4830,9)
        
    @property
    def styles(self):
        """
        Returns a dictionary object with mapserver styles for the all the 
        output attributes of this model.
        
        Todo: This is a little messy at the moment. Consider using the template
              engine in Flask (which is Jinja) for rendering these snippets
              using a separate template.
        """
        styles={}
        for attribute in self.reporting:
            symbolizer=self.reporting[attribute]['symbolizer']
            colors=symbolizer["colors"]
            values=symbolizer["values"]
            labels=symbolizer.get("labels",[])
            
            style="# Style symbolizer (type=%s) for attribute: %s"%(symbolizer["type"],attribute)
            if symbolizer["type"]=="pseudocolor":
                steps=np.linspace(values[0],values[-1],num=len(colors))
                #style="\n#symbolizer: %s - colorsteps:%s"%(attribute,",".join(map(str,steps)))
                
                for i in xrange(0,len(colors)-1,1):
                    c1=colors[i]
                    c2=colors[i+1]
                    v1=steps[i]
                    v2=steps[i+1]
                    style+="""       
        CLASS
          EXPRESSION ([pixel] >= %f AND [pixel] < %f)
          STYLE 
            COLORRANGE "%s" "%s"
            DATARANGE %f %f
          END
        END
    """%(v1,v2,c1,c2,v1,v2)
                
            if symbolizer["type"]=="categorical":
                style+="#Categorical styles in here..."
                for (color,value,label) in zip(colors,values,labels):
                    style+="""       
        CLASS
          NAME "%s"
          EXPRESSION ([pixel] == %s)
          STYLE 
            COLOR "%s"
          END
        END
    """%(label,str(value),color)
                
            if symbolizer["type"]=="classified":
                style+="#Classified styles in here..."
                for i in xrange(0,len(values)-1,1):
                    c1=colors[i]
                    v1=values[i]
                    v2=values[i+1]
                    label=labels[i]
                    style+="""       
        CLASS
          NAME "%s"
          EXPRESSION ([pixel] >= %f AND [pixel] < %f)
          STYLE 
            COLOR "%s"
          END
        END
    """%(label,v1,v2,c1)
                
                
            styles.update({attribute:style})
        return styles
        


class ModelConfiguration(db.Model):
    """
    Describes a configuration for a model. This may be changed on the fly
    by users. This should contain all the necessary info to be able to 
    run a specific model with a specific configuration.

    Id by: model - discretization - parameterset

    Todo: integrate this better with generating the keys, that should also
    happen here. Something like a get_or_create type of function.
    
    All maps are also fetched initially by configuration key:
    
    /maps/<config_key>/<attribute>/<timestamp>
    
    The config key is mapped to a mapserver map file.
    
    Todo: link to a model id from where to get params
    
    """
    __tablename__='modelconfiguration'
    id = db.Column(db.Integer(), primary_key=True)
    key = db.Column(db.String(32), nullable=False, unique=True, index=True)
    identifier = db.Column(db.String(1024), nullable=False)
    parameters = db.Column(JSON(), nullable=True)
    
    model_id = db.Column(db.Integer(), db.ForeignKey('model.id'))
    model = db.relationship('Model', backref='modelconfiguration')
    
    #user_id = db.Column(db.Integer(), db.ForeignKey('user.id'))
    def __init__(self,key,config_string,model,parameters={}):
        self.key=key
        self.identifier=config_string
        self.parameters=parameters
        self.model=model
        
    @property
    def shortkey(self):
        return self.key[0:6]
        
    @property 
    def model_start(self):
        """
        Determine the model start time from the __start__ parameter. 
        """
        return datetime.datetime.strptime(self.parameters.get("__start__",None),"%Y-%m-%dT%H:%M:%S")
        
    @property
    def model_timesteps(self):
        """
        Returns a list of timestamps moving forward from the model's start
        point as defined by the '__start__' parameter.
        """
        model_start = self.model_start
        timestamp_list = []
        
        #get the number of timesteps as well as the length of each timestep
        #from the Model associated with this ModelConfiguration
        model_timesteps = self.model.time['timesteps']
        model_timesteplength = self.model.time['timesteplength']

        for timestep in range(model_timesteps):
            seconds_to_add = (timestep) * model_timesteplength
            timestamp = (model_start + datetime.timedelta(seconds=max(0,seconds_to_add)))
            timestamp_list.append(timestamp.isoformat())
        
        return timestamp_list
        
    @property
    def as_dict(self):
        """
        Return a JSON representation of a modelconfiguration.
        """
        return {
            "model":self.model.as_dict,
            "parameters":self.parameters,
            "timesteps":self.model_timesteps,
            "results":self.results
        }
    
    @property
    def results(self):
        """
        Return a list of results for this modelconfiguration.
        """
        maps=db.session.query(Map.timestamp,Map.attribute).filter_by(modelconfiguration_id=self.id).group_by(Map.timestamp,Map.attribute).order_by(Map.timestamp).all()
        results={
            "timesteps":[],
            "attributes":[],
            "config_key":self.key
        }
        previous_timestamp=None

        for (timestamp,attribute) in maps:
            if previous_timestamp!=timestamp:
                results["timesteps"].append({"attributes":{},"timestamp":timestamp.isoformat()})
            results["timesteps"][-1]["attributes"].update({attribute:True})
            previous_timestamp=timestamp
        
        return results
        
    def update_mapserver_configuration(self):
        """
        Update the mapserver configuration file for the model configuration.
        
        A list of all attribute maps created with this configuration can be
        accessed through the backref self.maps
        
        todo: do this after each chunk is completed, or after each job is completed?
        """
        print " * Updating mapserver configuration for config %s"%(self.shortkey)
        
        mapserver_template=render_template('mapserver/page.map',page=self,modelconfiguration=self)
        with open(os.path.join("/var/mapserver/maps","%s.map"%(self.key)),'w') as f:
            f.write(mapserver_template)
        return True
    @property
    def layer_list(self):
        """
        Returns a list of layers that are available for this configuration.
        """
        #return Map.query.filter_by(modelconfiguration_id=self.id).distinct(Map.attribute).all()
        #return self.maps.distinct(Map.attribute)
        return list(db.session.query(Map.attribute.distinct()).filter_by(modelconfiguration_id=self.id).group_by(Map.attribute).all())


class Job(db.Model):
    """
    Describes a processing request which consists of an area for which to 
    run the model (defined by geom) and a configuration with which to run
    the model, which is defined by a link to a ProcessingConfig.

    A backref from "processingjobs" lists the individual jobs which make up
    this request.

    Job stores the: 
        - model
        - bbox

    Configuration (model parameters only) are stored in ModelConfiguration

    JobChunks are dumped in a queue, workers can use them to run model,
    but config is not part of the chunk but of the job. can be included 
    in the queue for simplicity, but better to define a queue job as
    the dict of a JobChunk

    Todo: shouldnt the modelconfiguration store the model to run with??
    """
    __tablename__='job'
    id = db.Column(db.Integer(), primary_key=True)
    uuid = db.Column(UUID, index=True)
    date_created = db.Column(db.DateTime(), nullable=False, default=db.func.now())
    date_completed = db.Column(db.DateTime(), nullable=True)
    user_id = db.Column(db.Integer(), db.ForeignKey('user.id'))
    
    modelconfiguration_id = db.Column(db.Integer(), db.ForeignKey('modelconfiguration.id'))
    modelconfiguration = db.relationship('ModelConfiguration', backref='jobs')
    
    geom = db.Column(Geometry(geometry_type='POLYGON', srid=4326))
    status_code = db.Column(db.Integer(), nullable=False, default=0)
    status_message = db.Column(db.String(512), nullable=True)
    status_log = db.Column(db.Text(), nullable=True)
    def __init__(self,modelconfig,chunks,geom):
        """
        Create this job. Fetch and assign the required 'chunks automatically
        upon creation and store in database. Synopsis:

        - set self.geom to the bbox
        - set the uuid
        - set the model and user id
        - create a model configuration with all the other params
        - add the jobchunks to this job
        - return a job uuid
        """
        self.modelconfiguration=modelconfig
        self.uuid=str(uuid.uuid4())
        self.status_message="yay for this job!"
        self.geom=geom
        print "Creating new job instance"
        for chunk_id in chunks:
            print " Add chunk %d to job..."%(chunk_id)
            jobchunk=JobChunk(job_id=self.id,chunk_id=chunk_id)
            self.jobchunks.append(jobchunk)
        print "Finished creating job instance"

    @property
    def shortkey(self):
        return str(self.uuid)[0:6]
        
    @property
    def shortdate(self):
        return self.date_created.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def jobchunks_list(self):
        """
        Returns a list of job chunk uuids which can be posted to the processing queue.
        """
        return [str(jc.uuid) for jc in self.jobchunks.all()]

    @property
    def jobchunks_total(self):
        return self.jobchunks.count()

    @property
    def jobchunks_completed(self):
        return self.jobchunks.filter_by(status_code=1).count()

    @property
    def jobchunks_failed(self):
        return self.jobchunks.filter_by(status_code=-1).count()

    @property
    def jobchunks_status(self):
        _total=self.jobchunks_total
        _completed=self.jobchunks_completed
        _failed=self.jobchunks_failed
        if _total==_completed:
            return "COMPLETED"
        if _failed > 1:
            return "FAILED"
        return "PROCESSING"
    @property
    def is_complete(self):
        if self.status_code!=1:
            return False
    @property
    def percent_complete(self):
        """
        Return a percentage complete of this job (0-100). 
        
        Todo: use self.jobchunks instead of filter_by(job_id=self.id)
        """
        (status_percentdone,)=db.session.query(func.avg(JobChunk.status_percentdone).label('average')).filter_by(job_id=self.id).first()
        return int(status_percentdone)
        
    @property
    def time_remaining(self):
        """
        Return an approximation of the time remaining in sec for this job. If
        the job is completed 0 is returned.
        """
        return 100
        
    @property
    def status_codes(self):
        """
        Return a list of status codes of the JobChunks that belong to this 
        Job. The status of the job depends on these codes. If all the JobChunks
        are completed, then so is the Job. If one of the chunks encountered an
        error, then the Job has an error too.
        """
        status_codes=db.session.query(JobChunk.status_code.distinct()).filter_by(job_id=self.id).all()
        return [s[0] for s in status_codes]
        
    def update_status(self):
        status_codes=self.status_codes
        if status_codes==[1]:
            self.status_code=1
        if -1 in status_codes:
            self.status_code=-1
        if 0 in status_codes:
            self.status_code=0
        db.session.commit()
        
    @property
    def results(self):
        """
        Return a dict of maps which are the result of this job. However, these 
        maps are not directly linked to this job, but rather linked to the
        modelconfiguration. This is because after a job is done, all maps 
        with the same modelconfiguration should be shown, even if they were
        calculated some other time in a different area.. they all make up
        one attribute layer calculated with a certain model and param set.
        
        A dict is returned like the following:
        
        {
            "<attribute>":["<timestamp>","<timestamp>" (...) ]        
        }
        
        This result is used by the web interface to know for which attributes
        and at what times there is data available.
        """
        if self.status_code != 1:
            return []
        else:
            return self.modelconfiguration.results
        


class JobChunk(db.Model):
    """
    Describes a single independent job which can be run by a worker. Contains keys to:

        - A chunk which needs to be processed
        - A job (+model +configuration +direcretization) to which this jobchunk belongs
        - A jobchunk id for sending updates.
    
    With this information the worker can access the API, get the config and the input
    maps, and do its job.
    
    todo:add percent_complete field instead
    """
    __tablename__='jobchunk'
    id = db.Column(db.Integer(), primary_key=True)
    uuid = db.Column(UUID, index=True)
    chunk_id = db.Column(db.Integer(), db.ForeignKey('chunk.id'))
    #modelconfiguration_id = db.Column(db.Integer(), db.ForeignKey('modelconfiguration.id'))
    job_id = db.Column(db.Integer(), db.ForeignKey('job.id'))
    job = db.relationship('Job', backref=db.backref('jobchunks', lazy='dynamic'))
    status_code = db.Column(db.Integer(), nullable=False, default=0)
        # -1=FAILED
        #  0=CREATED/WAITING
        # +1=COMPLETEDSUCCESSFUL
    status_message = db.Column(db.String(512), nullable=True)
    status_log = db.Column(db.Text(), nullable=True)
    status_percentdone = db.Column(db.Integer(), nullable=False, default=0)
    time_started = db.Column(db.DateTime(),nullable=True, index=True)
    time_completed = db.Column(db.DateTime(),nullable=True, index=True)
    
    def __init__(self,job_id,chunk_id):
        self.uuid=str(uuid.uuid4())
        self.chunk_id=chunk_id
        self.job_id=job_id

    @property
    def shortkey(self):
        return str(self.uuid)[0:6]        
        
    @property
    def as_dict(self):
        return {
            'jobchunk_id':self.uuid,
            'status_code':self.status_code,
            'status_message':self.status_message
        }
        

    @property
    def pickled(self):
        """
        Returns a pickled representation of this JobChunk that is posted
        straight into the beanstalk queue for processing by backend workers.
        """
        return cPickle.dumps({
            'uuid_jobchunk':str(self.uuid),
            'uuid_chunk':str(self.chunk.uuid),
            'config_key':str(self.job.modelconfiguration.key),
            'api_url':'http://127.0.0.1:5000/api/v1',
            'parameters':self.job.modelconfiguration.parameters,
            'grid':self.chunk.grid,
            'modelcode':self.job.modelconfiguration.model.code
        })


class User(db.Model, UserMixin):
    """
    User table for user management.
    """
    __tablename__='user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    active = db.Column(db.Boolean(), nullable=False, default=False)
    fullname = db.Column(db.String(50), nullable=True, unique=False, default='')
    password = db.Column(db.String(255), nullable=False, default='')
    email = db.Column(db.String(255), nullable=False, unique=True)
    confirmed_at = db.Column(db.DateTime())
    reset_password_token = db.Column(db.String(100), nullable=False, default='')
    roles = db.relationship('Role', secondary='user_roles', backref=db.backref('users', lazy='dynamic'))
    
    def __repr__(self):
        return "<User: %s>"%(self.username)
        
    def has_role(self,role_name):
        """
        Returns True if a user has a role with name <role_name>, False otherwise
        """
        for role in self.roles:
            if role.name==role_name:
                return True
        return False
        
    @property
    def is_admin(self):
        """
        Returns True is user has an admin role, False otherwise.
        """
        return self.has_role("admin")

# Define the UserRoles DataModel
class UserRoles(db.Model):
    __tablename__="user_roles"
    id = db.Column(db.Integer(), primary_key=True)
    user_id = db.Column(db.Integer(), db.ForeignKey('user.id', ondelete='CASCADE'))
    role_id = db.Column(db.Integer(), db.ForeignKey('role.id', ondelete='CASCADE'))

# Define the Role DataModel
class Role(db.Model):
    __tablename__="role"
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(50), unique=True)

