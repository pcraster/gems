import os
import uuid
import pyproj

import hashlib
import random
import re
import sys
import beanstalkc 
import json
import utm
import cPickle
import datetime
import time 
import shutil
import numpy as np

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

from subprocess import check_output

from utils import create_configuration_key, parse_model_time

db = SQLAlchemy()

class BeanstalkConnectionFailure(Exception):
    pass

class BeanstalkWorkersFailure(Exception):
    pass

class Beanstalk(object):
    """
    Wrapper to manage the beanstalk connection and prevent socket errors from
    occurring in the web app. You can check if the beanstalk connection is
    still active, this will check the __nonzero__ method:
    
    if beanstalk:
        #active
    else:
        #not active
    
    If the connection has been closed for whatever reason, checking "if beanstalk"
    will also try to reconnect once. If that reconnect also fails, then False is
    returned. If the queue is connected True is returned.
    
    To access the actual beanstalk queue, use beanstalk.queue, which will return
    the beanstalk connection object directly. Here too the connection is checked,
    and if there is no connection then it is retried.
    
    Todo: Figure out if this is the best way to manage the beanstalk connection,
    it's a bit improvised but should be adequate for now.
    """
    def __init__(self):
        """
        Initialize the object.
        """
        self.tubename = 'gemsjobs'
        c = self.connect()

    def __nonzero__(self):
        """
        Return a boolean if the connection is active. This is used when 
        "if beanstalk: (...)" is used in the code.
        """
        return True if self.queue else False

    def connect(self):
        """
        Connect to the work queue and checks whether the connection actually
        works.
        """
        try:
            self._conn = beanstalkc.Connection('localhost', port=11300)
            self._conn.use(self.tubename)
            if self._conn.using() != self.tubename:
                return False
        except:
            return False
        else:
            return True

    def reconnect(self):
        """
        Attempts to reconnect to the queue.
        """
        try: 
            self._conn.reconnect()
            self._conn.use(self.tubename)
        except: 
            return False
        else: 
            return self.connected
            
    def tube_clear(self):
        """
        Forces clearing of the entire queue. This happens for example when the
        install procedure takes place, or from a button on the processing page.
        """
        while True:
            job = self._conn.reserve()
            job.delete()
    
    def tube_stats(self, statistic):
        stats = self._conn.stats_tube(self.tubename)
        if statistic in stats:
            return stats[statistic]
        else:
            return None
        
    @property
    def ok(self):
        return True if self.workers else False
        
    @property
    def workers_watching(self):
        return True if self.workers else False
        
    @property
    def jobs_in_queue(self):
        return self.tube_stats('current-jobs-ready')
            
    @property
    def workers(self):
        """
        Property which uses the connection stats of the gems jobs tube and
        returns the 'current-watching' stats element to check how many workers
        are currently watching the tube for new jobs.
        """
        try:
            stats = self._conn.stats_tube(self.tubename)
            if 'current-watching' in stats:    
                return stats['current-watching']
            else:
                return 0
        except:
            return 0

    @property
    def queue(self):
        """
        Returns the connection object of the queue.
        """
        if self.connected:
            return self._conn
        else:
            return self._conn if self.reconnect() else False
            
    @property
    def connected(self):
        """
        Uses the connection's using() method to check that the connection is
        still active.
        """
        try: 
            tube = self._conn.using()
            if tube != self.tubename:
                return False
        except: 
            return False
        else: 
            return True
            
    @property
    def status(self):
        try:
            status = self._conn.stats_tube(self.tubename)
        except:
            return None
        else:
            return status

beanstalk = Beanstalk()

def generate_api_token():
    return ''.join(random.choice("abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(32))
    
def random_password():
    return ''.join(random.choice("abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))

class Discretization(db.Model):
    """This class describes the SQLAlchemy data model for Discretizations in
    GEMS. The following attributes are defined as SA columns represented in 
    the corresponding database table.
    
    * :attr:`~webapp.models.Discretization.id` (Integer)
    * :attr:`~webapp.models.Discretization.name` (String)
    * :attr:`~webapp.models.Discretization.description` (String)
    * :attr:`~webapp.models.Discretization.cellsize` (Integer)
    * :attr:`~webapp.models.Discretization.num_of_chunks` (Integer)
    * :attr:`~webapp.models.Discretization.buffer_` (Integer)
    * :attr:`~webapp.models.Discretization.coverage` (Multipolygon Geometry)
    * :attr:`~webapp.models.Discretization.extent` (Polygon Geometry)
    """
    
    __tablename__ = 'discretization'
    """Table name where discretizations are stored."""
    
    id = db.Column(db.Integer(), primary_key=True)
    """ID of this disretization."""
    
    name = db.Column(db.String(512), unique=True, nullable=False, index=True)
    """Name of this discretization."""
    
    description = db.Column(db.String(1024), unique=False, nullable=True, \
        index=False)
    """Description of this discretization."""
    
    cellsize = db.Column(db.Integer(), nullable=False, default=100)
    """The cell size that models being run on this chunk should use. Defaults 
    to 100."""
    
    num_of_chunks = db.Column(db.Integer(), nullable=False)
    """The number of individual chunks in this discretization."""
    
    buffer_ = db.Column(db.Integer(), nullable=False, default=1000)
    """A buffer value that should be applied around the perimeter of the chunks 
    in this discretization. **Not in use.**"""
    
    coverage = db.Column(Geometry(geometry_type='MULTIPOLYGON', srid=4326))
    """A multipolygon geometry representing a simplified coverage of all the 
    chunks in this chunkscheme. This is used to create the overview shapes on
    the "discretizations" admin page. The coverage is simplified to avoid 
    having to load thousands of chunks when trying to display the area covered
    by for example the "world_onedegree" discretization. The coverage is set 
    once when the discretization is first created. Defined in SA as: 
    ``Geometry(geomtry_type='MULTIPOLYGON', srid=4326)``."""
    
    extent = db.Column(Geometry(geometry_type='POLYGON', srid=4326))
    """A polygon geometry which is an envelope of the coverage polygon. This is
    used to quickly establish where a certain chunkscheme is valid and to 
    position the map accordingly. For example, when you load a model which
    uses the "world_onedegree" chunkscheme, the initial map view is positioned
    so that this extent is visible. The extent is set once when the 
    discretization is first created. Defined in SA as: 
    ``Geometry(geometry_type='POLYGON', srid=4326)``."""

    def __repr__(self):
        """Returns a text representation of this discretization."""
        return "<Discretization: %s>"%(self.name)

    def __init__(self, name="", dataset=None, cellsize=100):
        """Creates a new discretization and corresponding chunks. An exception
        is raised when something failed during the creation process.
        
        :param str name: Name of the discretization. Do not use any non-word
            characters. The actual name will be modified by appending the cell
            size to it.
        :param int cellsize: Cell size in meters. Choose this value with care!
            Creating a discretization with chunks the size of France and a cell
            size of 100m will create enormous raster files for each model run,
            probably bringing the system to a halt. 
        :param GDALDataset dataset: Instance of a GDALDataset which contains 
            polygon features. Each polygon will be turned into a Chunk within
            this discretization.
            
        .. note::
        
            Keep the following in mind when creating Discretizations yourself:
        
            * In the discretization name any (consequetive) non-word characters 
              will be replaced with an underscore, and the cellsize will be 
              appended to the final discretization name. For example, creating
              a discretization with the ``name="world onedegree"`` and 
              ``cellsize=100`` will end up with the name 
              ``world_onedegree_100m``.
              
            * Only geometries of type POLYGON will be converted to chunks and 
              coupled to this Discretization.
            
            * Only datasets with features in WGS84 latlng coordinates (epsg:
              4326) will be accepted.
            
        .. todo::
        
            It would be interesting to create a "description" or "search terms"
            field which contains attributes such as a name of the features. 
            The search functionality in the web app could then include these
            terms. In such a scenartio, if we have a chunk scheme of US 
            Counties, we could search for a county by name and jump straight 
            to it. Another possibility would be to add attribute fields to the
            selected (with the red outline) chunk in the web interface. Such
            functionality is pretty low-priority though.
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
            raise Exception("Shapes must be in unprojected WGS84 latlng coordinates (epsg 4326)")
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
            
        #print "Found %d polygon features."%(num_of_chunks)
        self.num_of_chunks=num_of_chunks
            
        #print "Creating cascaded union... This may take a while if your polygons are complicated..."
        #chunk_polygons = MultiPolygon(polygons=[loads(wkt).buffer(0.01) for wkt in polygons])
        chunk_extents = MultiPolygon(polygons=[box(*loads(wkt).buffer(0.01).bounds) for wkt in polygons])
        chunk_union = cascaded_union(chunk_extents)
        chunk_union.simplify(0.01)
        
        if chunk_union.geom_type == 'Polygon':
            # If all the chunks were connected to each other then a Polygon is
            # is created rather than a MultiPolygon. Our database column needs
            # a MultiPolygon, so convert it before saving it.
            chunk_union = MultiPolygon([chunk_union])

        chunk_box = box(*chunk_union.bounds)

        self.coverage = from_shape(chunk_union, srid=4326)
        self.extent = from_shape(chunk_box, srid=4326)
        #print "Storing..."
        
    @property
    def extent_as_bounds(self):
        """Return the discretization extent as a comma-separated string of 
        coordinates."""
        bounds = to_shape(self.extent).bounds
        return ",".join(map(str,bounds))
        
    @property
    def coverage_as_geojson(self):
        """Return the discretization coverage as a GeoJSON string."""
        cov = to_shape(self.coverage)
        return json.dumps(mapping(cov))
        
class Chunk(db.Model):
    """This class describes the SQLAlchemy data model for Chunks in GEMS. The
    following attributes are defined as SA columns represented in the 
    corresponding database table.
    
    * :attr:`~webapp.models.Chunk.id` (Integer)
    * :attr:`~webapp.models.Chunk.discretization_id` (Integer)
    * :attr:`~webapp.models.Chunk.uuid` (UUID)
    * :attr:`~webapp.models.Chunk.geom` (Polygon Geometry)
    
    The following relationships to other models are defined:
    
    * :attr:`~webapp.models.Chunk.discretization` (Relationship to a :class:`~webapp.models.Chunk`)
    * :attr:`~webapp.models.Chunk.jobchunks` (Relationship to a :class:`~JobChunk`)
    """
    
    __tablename__ = 'chunk'
    """Name of the table where this model is stored."""
    
    id = db.Column(db.Integer(), primary_key=True)
    """SA column containing the ID of this chunk."""
    
    discretization_id = db.Column(db.Integer(), db.ForeignKey('discretization.id'))
    """SA column containing the ID of the discretization to which this chunk 
    belongs."""
    
    discretization = db.relationship('Discretization', backref=db.backref('chunks', lazy='dynamic'))
    """SA relationship to a Discretization instance."""
    
    jobchunks = db.relationship('JobChunk', backref='chunk', lazy='dynamic')
    """SA relationship to a JobChunk instance."""
    
    uuid = db.Column(UUID, index=True)
    """SA column containing the UUID of this chunk."""
    
    geom = db.Column(Geometry(geometry_type='POLYGON', srid=4326))
    """SA column containing the Polygon Geometry of this chunk."""
    
    def __init__(self, wkt_polygon):
        """Creates a new chunk from a polygon in WKT (Well-Known Text) format.
        Usually chunks are created automatically when a 
        :class:`~webapp.models.Discretization` is made, so you'll usually won't
        have to do this yourself. Chunks which are not part of any
        discretization cannot be used.
        
        :param str wkt_polygon: String with a WKT polygon in it. Must be in 
            unprojected Lat-Long format.
        """
        polygon = loads(wkt_polygon)
        self.uuid = str(uuid.uuid4())
        self.geom = from_shape(polygon, srid=4326)
        
    @property
    def grid(self):
        """Property returning a dictionary (grid) representation of this chunk, 
        including the bounding box, geotransform variables, cellsize, rows, 
        cols, etc. This information is used to construct a grid, a clone map, 
        and a mask  on which the model will be run by the workers. The Chunk's 
        grid property is also used to construct the JobChunk posted into the 
        work queue.
        """
        geom = to_shape(self.geom)
        return {
            'bounds':geom.bounds,
            'bbox':self.bbox,
            'bbox_utm':self.bbox_utm,
            'bbox_latlng':self.bbox_latlng,
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
        """EPSG code of the UTM zone in which this Chunk is located. :py:`int`
        """
        epsg = 32600
        geom = to_shape(self.geom)
        easting, northing, zone, zone_letter = utm.from_latlon(geom.centroid.y, geom.centroid.x) 
        if zone_letter<'N': #southern zones get +100
            epsg+=100
        return epsg+zone

    @property
    def cellsize(self):
        """Cell size of the discretization to which this chunk belongs. (int)
        """
        return self.discretization.cellsize
        
    @property
    def pixelwidth(self):
        """Integer width of a single pixel of this chunk."""
        (minx, miny, maxx, maxy) = self.bbox
        return (maxx-minx)/self.cols

    @property
    def pixelheight(self):
        """Returns the height of a single pixel of this chunk."""
        (minx, miny, maxx, maxy) = self.bbox
        return (miny-maxy)/self.rows        
        
    @property
    def bbox(self):
        """Returns the UTM bounding box of this chunk."""
        return self.bbox_utm
    
    @property
    def bbox_utm(self):
        """Returns the UTM bounding box of this chunk."""
        project = partial(pyproj.transform, pyproj.Proj(init="epsg:4326"), \
            pyproj.Proj(init="epsg:%d"%(self.srid)))
        return transform(project,to_shape(self.geom)).bounds
        
    @property
    def bbox_latlng(self):
        """Returns a Lat-Lng bounding box of this chunk."""
        geom = to_shape(self.geom)
        return geom.bounds
        
    @property
    def mask(self):
        """Returns a geometry in the local UTM projection defined in this 
        chunk's ``srid`` property."""
        project=partial(pyproj.transform, pyproj.Proj(init="epsg:4326"), \
            pyproj.Proj(init="epsg:%d"%(self.srid)))
        return transform(project,to_shape(self.geom))
        
    @property
    def rows(self):
        """Return the number of rows that this chunk has in the local utm
        projection."""
        bbox=self.bbox
        return int(round((bbox[3]-bbox[1])/self.cellsize))

    @property
    def cols(self):
        """Return the number of cols that this chunk has in the local utm
        projection."""
        bbox=self.bbox
        return int(round((bbox[2]-bbox[0])/self.cellsize))
        
    @property
    def projection(self):
        """Returns a projection string in WKT format of the UTM zone that this
        chunk falls in."""
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(self.srid) 
        return ref.ExportToWkt()
        
    @property
    def geotransform(self):
        """Returns the 6 coefficients which map pixel/line coords into a 
        georeferenced space. These coordinates are a function of self.bbox and
        self.cellsize and are assigned to output datasets using gdal's 
        SetGeoTransform function.
        
        The coefficients are (left, pixelwidth, 0, top, 0, pixelheight)"""
        (minx, miny, maxx, maxy) = self.bbox
        return (minx, self.pixelwidth, 0, maxy, 0, self.pixelheight)


class Map(db.Model):
    """Describes a single attribute map generated by a model. All maps or 
    output attributes created by a model must be uniquely identifiable by four 
    criteria:
    
    * A **ModelConfiguration** instance. This describes the set of 
      configuration parameters that were used to create the attribute value
      stored in the map.
    
    * A **Chunk** instance. This describes the area which is represented 
      in the map.
      
    * An **attribute name** which was given when the map was reported in the 
      model script.
      
    * A **timestamp** which is representative of the timestep in which this map
      was reported.
      
    Some of the data for these criteria is part of other models (such as 
    the extent which is defined by a Chunk instance, or a configuration key
    which is defined by a ModelConfiguration instance. The relevant 
    information from these models is straight up copied into the Map 
    data model rather than just referenced using an SQLAlchemy 
    relationship. The reason for this is that other applications (in this 
    case Mapserver) make use of the map table to display WMS maps of the 
    output attribute given the four criteria mentioned above, and that 
    Mapserver cannot follow, sort, select, or create tile indexes via such 
    SQLAlchemy relationships. For these types of purposes we need a single 
    table with clear attributes which can then be easily sorted and 
    selected upon. 
      
    .. note::
    
        The actual map raster data is not stored in the database, but a
        reference to a VRT (virtual dataset) is stored in the "filename" 
        attribute. The VRT in turn points to a specific band in a compressed
        and optimized GeoTIFF file in which the actual raster values are 
        stored.
              
    .. note::
    
        Backreferences named **maps** are defined on the ModelConfiguration
        and Chunk models. That way, for example if you have a Chunk or
        ModelConfiguration instance you can query all the maps created with 
        that configuration by looping over the ModelConfiguration's 'maps' 
        attribute.
        
    """
    
    __tablename__='map'
    """Table name where map data is stored."""
    
    id = db.Column(db.Integer(), primary_key=True)
    """ID of the map instance."""

    modelconfiguration_id = db.Column(db.Integer(), db.ForeignKey('modelconfiguration.id'))
    """ID of the ModelConfiguration instance that was used to create the data
    present in this map."""
    
    modelconfiguration = db.relationship('ModelConfiguration', backref='maps')
    """SA relationship to the ModelConfiguration instance."""
    
    config_key = db.Column(db.String(32), nullable=False, unique=False, index=True)
    """Text representation of the configuration key defined in the related
    ModelConfiguration instance. This is one of the attributes that Mapserver
    needs to sort by to display this map as a WMS service."""
    
    timestamp = db.Column(db.DateTime(), nullable=True, index=True)
    """Timestamp field representing the model timestep at the time when this
    map was reported. This is one of the attributes that Mapserver needs to
    sort by to display this map as a WMS service."""
    
    attribute = db.Column(db.String(1024), nullable=False, index=True)
    """The model output attribute that this map represents. This is one of the 
    attibutes that Mapserver needs to sort by to display this map as a WMS 
    service."""
    
    chunk_id = db.Column(db.Integer(), db.ForeignKey('chunk.id'))
    """ID of the Chunk that this map was created on."""
    
    chunk = db.relationship('Chunk', backref='maps')
    """SA relationship to the Chunk instance that this Map was originally
    created on."""
    
    geom = db.Column(Geometry(geometry_type='POLYGON', srid=4326))
    """Geometry in Lat-Lng representing the extent of this Map. The geometry 
    is copied from the related Chunk's extent."""
    
    geom_web_mercator = db.Column(Geometry(geometry_type='POLYGON', srid=3857))
    """Geometry in Pseudo Mercator representing the extent of this Map. The 
    geometry is copied/reprojected from the related Chunk's extent to be able 
    to let Mapserver use the spatial index as well as having to avoid
    on-the-fly reprojections."""
    
    datatype = db.Column(db.String(1024), nullable=False, index=False)  
    """Datatype of this map."""
    
    filename = db.Column(db.String(1024), nullable=False, index=False)
    """Filename pointing to the VRT (virtual dataset) of this Map."""
    
    filesrs = db.Column(db.String(2048), nullable=True, index=False, default='')
    """The spatial reference system of the file specified in the "filename"
    attribute. This will be an SRS corresponding to the UTM zone that the data
    was created in by the model. Mapserver needs this field to be able to 
    stitch together different files (defined by filename) which are in 
    different projections."""

    def __repr__(self):
        """Text representation of this map."""
        return "<Map config=%s chunk=%s time=%s filename=%s>"%(self.config_key[0:6],self.chunk.uuid[0:6],self.timestamp.isoformat(),self.filename) 
        
    def __init__(self, chunk, modelconfiguration, options):
        """Creates a new Map.
        
        :param Chunk chunk: Chunk instance that this Map is created on.
        :param ModelConfiguration modelconfiguration: ModelConfiguration 
            instance that was used to generate this map.
        :param dict options: Dictionary containing additional data about this 
            map, such as keys for the attribute name, filesrs, datatype, and
            timestamp.
        
        .. note::
        
            Map instances are typically created by the API upon receiving a 
            maps package, which is the result of a model run. The maps 
            package will contain a manifest JSON file listing all the files in
            the maps package as well as its attributes, timestamps, config key,
            etc. for each map. Each entry in the manifest of the maps package 
            is turned into a Map instance in the database by the API endpoint
            receiving the maps package upload.
            
            The mapserver configuration files for each model use the map table
            to create WMS services.
        """
        self.chunk=chunk
        self.modelconfiguration=modelconfiguration
        self.config_key=modelconfiguration.key
        self.geom=chunk.geom
        
        project=partial(pyproj.transform, pyproj.Proj(init="epsg:4326"), pyproj.Proj(init="epsg:3857"))
        self.geom_web_mercator=from_shape(transform(project,to_shape(self.geom)),3857)        
        
        self.attribute=options["attribute"]
        self.filename=os.path.join(current_app.config["HOME"],"maps",options["filename"])
        self.filesrs=options["filesrs"]
        self.datatype=options["datatype"]
        self.timestamp=datetime.datetime.strptime(options["timestamp"], "%Y%m%d%H%M%S")
    
class Model(db.Model):
    """Describes an environmental model which can be run in the GEMS 
    environment.

    Todo:
        - add owner
        - add last updated
        - use a getter and setter for the code attribute
        - use templates for generating mapserver config
        - clean up and refactor code
        - automatically fill in some demo code.

    """

    __tablename__='model'
    """Tabla name used to store the model"""
    
    id = db.Column(db.Integer(), primary_key=True)
    """ID of the model"""
    
    name = db.Column(db.String(512), unique=True, nullable=False, index=True)
    """Model name"""
    
    abstract = db.Column(db.Text(), unique=False, nullable=True)
    """Short description of the model functionality."""    
    
    contact = db.Column(db.String(512), unique=False, nullable=True)
    """Short contact information for the model creator."""

    #jobs = db.relationship('Job', backref='model', lazy='dynamic')

    disabled = db.Column(db.Boolean(), nullable=False, default=False)    
    """Boolean property indicating whether this model is enabled or not."""
    
    highlighted = db.Column(db.Boolean(), nullable=False, default=True)
    """Boolean property indicating whether this model is visible to all users
    or if it should show up in the "Hidden models" section of the GEMS 
    homepage."""
    
    validated = db.Column(db.Boolean(), nullable=False, default=False)
    """Boolean property indicating whether the model's Python code could be 
    imported successfully and it's properties could be read. If a model is not
    validated it cannot be run because it would just cause an error anyway."""
    
    modified = db.Column(db.DateTime(), nullable=True)
    """Date field signifying when the model was last updated."""
    
    discretization_id = db.Column(db.Integer(), db.ForeignKey('discretization.id'))
    """ID of the Discretization that this model should run on."""
    
    discretization = db.relationship('Discretization', backref='models')
    """SA relationship to a Discretization instance."""
    
    version = db.Column(db.Integer(), default=1)
    """Integer value representing the version/revision of the model. This value
    is incremented each time the model is successfully saved."""
    
    modelcode = db.Column(db.Text(), nullable=True, unique=False)
    """Python model code. 
    
    .. todo:
        Find out if this is still in use.
    """

    meta = db.Column(JSON(), nullable=True)
    """JSON property containing the values defined in the "meta" class
    attribute of the model code. This value is updated every time the model
    is successfully saved.
    
    :return: dictionary of metadata
    
    :param arg1: first param descr
    
    :type arg1: type description    
    
    :rtype: dict
    
    
    :Example:

        .. code-block:: python
            
            import module
    
    
    """    
    
    parameters = db.Column(JSON(), nullable=True)
    """JSON property containing the values defined in the "parameters" class
    attribute of the model code. This value is updated every time the model 
    is successfully saved."""
    
    time = db.Column(JSON(), nullable=True)
    """JSON property containing the values defined in the "time" class 
    attribute of the model code. This value is updated every time the model is
    successfully saved."""
    
    reporting = db.Column(JSON(), nullable=True)
    """JSON property containing the values defined in the "reporting" class
    attribute of the model code. This value is updated every time the model is
    successfully saved."""
    
    def __repr__(self):
        """Text representation of the model."""
        return "<Model: name=%s id=%d>"%(self.name,self.id)
        
    def __init__(self, name=None, code=None):
        """Creates a new model."""
        name = re.sub(r'\W+',' ',name).lower() #lowercase and remove non-word chars
        name = "_".join(map(str,name.split())) #replace one or more consequetive spaces with an underscore
        
        if name is None or len(name)==0:
            raise Exception("You need to specify a valid name.")
        
        m = Model.query.filter_by(name=name).first()
        if m is not None:
            raise Exception("A model with this name exists already.")
        
        self.name = name
        self.version = 0
        
        if code is None:
            code = render_template('new_model_template/new_model.py', model_name=self.name)

        self.updatecode(code)
        
    @property
    def as_dict(self):
        return {
            "meta":self.meta,
            "reporting":self.reporting,
            "time":self.time
        }
    
    @property
    def shortname(self):
        if len(self.name) >12:
            return self.name[:9]+"..."
        else:
            return self.name
        
    @property
    def filename(self):
        return os.path.join(self.filedir,"modelcode.py")
        
    @property
    def filenametest(self):
        return os.path.join(self.filedir,"modeltest.py")

    @property
    def filedir(self):
        _model_dir=os.path.join(current_app.config["HOME"],"models",self.name)
        if not os.path.isdir(_model_dir):
            print "model dir no exist..try to create... %s"%(_model_dir)
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
            
    def toggle_disable(self):
        self.disabled = False if self.disabled else True
        db.session.commit()
        return self.disabled   
        
    def toggle_pin(self):
        self.highlighted = False if self.highlighted else True
        db.session.commit()
        return self.highlighted

    def updatecode(self, code=""):
        """
        Attempts to update the model code. Returns True if successful and will
        raise an exception when something goes wrong.
        """
            
        if code == "":
            with open(self.filename,'w') as f:
                f.write(code)
            return True

        #write the provided code to a test file first.
        with open(self.filenametest,'w') as f:
            f.write(code)
            
        try:
            #try and load the model code
            sys.path.append(self.filedir)
            code_path = os.path.join(current_app.config["CODE"],"processing")
            sys.path.append(code_path)
            module = __import__("modeltest")
            model = getattr(module, "Model")
            m = model()
                    
#            print "meta:"
#            print m.meta
#            print "params:"
#            print m.parameters
        except Exception as e:
            raise Exception(e)
        else:
            #We loaded the model, now try and update the database           
            try:        
                #loaded model. update the code and the database model fields.
            
                #
                #check that the discretization used actually exists
                #
                if 'discretization' in m.meta:
                    d = Discretization.query.filter(Discretization.name==m.meta['discretization']).first()
                    if d is None:
                        raise Exception("The discretization '%s' which you defined in the 'meta' section does not exist."%(m.meta["discretization"]))
                    else:
                        self.discretization = d
                else:
                    raise Exception("No discretization defined in the 'meta' section.")
                    
                #todo: more error checking here on model parameters, time, or
                #datasources. 
                self.parameters=m.parameters
                self.time=m.time
                self.meta=m.meta
                self.reporting=m.reporting
                
                self.updateversion()
                self.validated=True
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                raise Exception(e)
            else:
                shutil.copy2(self.filenametest,self.filename)
                self.update_mapserver_template() #this step cannot be undone, so do it last.
            finally:
                del module
                del sys.modules["modeltest"]
                del m
                
        finally:
            #remove system paths
            sys.path.remove(self.filedir)
            sys.path.remove(code_path)
            
            #remove the intermediate testing files
            if os.path.exists(self.filename+"c"):
                os.remove(self.filename+"c")
            if os.path.exists(self.filenametest):
                os.remove(self.filenametest)
            if os.path.exists(self.filenametest+"c"):
                os.remove(self.filenametest+"c")
        
        
    def update_mapserver_template(self):
        """
        Updates the mapserver .map file for the outputs created by this model.
        """
        mapserver = {
            'version': 6,
            'postgis_connect':current_app.config.get("MAPSERVER_POSTGIS_CONNECT"),
            'debug':current_app.config.get("MAPSERVER_DEBUG",0)
        }
        
        try: mapserver_version_output = check_output([current_app.config.get("MAPSERVER_EXECUTABLE"),"-v"])
        except: mapserver_version_output = ""
        if mapserver_version_output.startswith("MapServer version 7"):
            mapserver["version"] = 7
        
        with open(self.mapserver_mapfile,'w') as f:
            mapserver_template=render_template('mapserver/page.map',model=self, mapserver=mapserver)
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
                if v != "###":
                    modelparams.update({k:v})

        #add the default parameters to the configuration as well
        modelparams.update({
            '__start__':            self.start.isoformat(),
            '__timesteps__':        self.time['timesteps'],
            '__discretization__':   self.discretization.name,
            '__model__':            self.name,
            '__version__':          self.version
        })

        #create a configuration with a configuration id for this job
        config_key,config_string,parameters=create_configuration_key(modelparams)

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
        Returns a default configuration key for this model by calling 
        configure() without any parameters. In this case the default params
        will be used.
        """
        modelconfig=self.configure()
        return modelconfig.key
        
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
    def maxchunks(self):
        """
        Returns the max number of chunks allowed in a model run.
        """
        try:
            maxchunks = int(self.meta["maxchunks"])
        except:
            maxchunks = 1
        return maxchunks
        
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
    def as_short_dict(self):
        """
        Return a JSON representation of a modelconfiguration.
        """
        return {
            "parameters":self.parameters,
            "meta":self.model.meta,
        }
        
    @property
    def as_text(self):
        params_as_str = "\n".join(["%s -> %s"%(param,str(self.parameters[param])) for param in sorted(self.parameters)])
        return """ModelConfiguration '%s' (id=%d)\n\n%s
        """%(str(self.key),self.id,params_as_str)
        
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
    user = db.relationship('User', backref='jobs')
    
    modelconfiguration_id = db.Column(db.Integer(), db.ForeignKey('modelconfiguration.id'))
    modelconfiguration = db.relationship('ModelConfiguration', backref='jobs')
    
    geom = db.Column(Geometry(geometry_type='POLYGON', srid=4326))
    status_code = db.Column(db.Integer(), nullable=False, default=0)
    status_message = db.Column(db.String(512), nullable=True)
    status_log = db.Column(db.Text(), nullable=True)
    def __init__(self,modelconfig,chunks,geom,user):
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
        self.user_id=user.id
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
    def shorterdate(self):
        if self.date_created.strftime('%U') == datetime.datetime.now().strftime('%U'):
            return self.date_created.strftime('%a %H:%M')
        else:
            return self.date_created.strftime('%d-%-m %H:%M')

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
            
    @property
    def as_text(self):
        """
        Returns a text/logfile representation of the Job.
        
        Todo: use a template.
        """
        chunk_list = ""
        for n,jc in enumerate(self.jobchunks.all()):
            chunk_list+="JobChunk '%s':  %s (%d)"%(jc.shortkey,jc.status,jc.status_code)
        
        log = """                               *** JOB LOG ***
===============================================================================
Job '%s' (id=%d)

Date:               %s
UUID:               %s
Status:             %s
Number of chunks:   %d (%d completed, %d failed)
===============================================================================
%s
===============================================================================
%s
===============================================================================
"""%(self.shortkey,self.id,self.shortdate,str(self.uuid),self.jobchunks_status,self.jobchunks_total,self.jobchunks_completed,self.jobchunks_failed,chunk_list,self.modelconfiguration.as_text)
        
        for n,jc in enumerate(self.jobchunks.all()):
            log+="""Chunk:              %d/%d"""%(n+1,self.jobchunks_total)
            log+=jc.as_text
        
        return log
        

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
    def status(self):
        if self.status_code == 0:
            return "PROCESSING"
        if self.status_code == -1:
            return "FAILED"
        if self.status_code == 1:
            return "COMPLETED"
        
    @property
    def as_dict(self):
        return {
            'jobchunk_id':self.uuid,
            'status_code':self.status_code,
            'status_message':self.status_message
        }
        
    @property
    def as_text(self):
        return """
Id:                 %s
Status code:        %d
Status message:     %s
Log:

%s



        """%(str(self.uuid),self.status_code,self.status_message,self.status_log)
        

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
    api_token = db.Column(db.String(32), nullable=False, unique=False, default=generate_api_token)
    roles = db.relationship('Role', secondary='user_roles', backref=db.backref('users', lazy='dynamic'))
    
    def __repr__(self):
        return "<User: %s>"%(self.username)
        
    def has_role(self, role_name):
        """
        Returns True if a user has a role with name <role_name>, False otherwise
        """
        for role in self.roles:
            if role.name==role_name:
                return True
        return False
        
    def toggle_role(self, role_name):
        """
        Toggle a user role
        """
        role = Role.query.filter(Role.name==role_name).first()
        if not self.has_role(role_name):
            self.roles.append(role)
            db.session.commit()
            return True
        else:
            self.roles.remove(role)
            db.session.commit()
            return False
        
    def add_role(self, role_name):
        if not self.has_role(role_name):
            role = Role.query.filter(Role.name==role_name).first()
            self.roles.append(role)
            db.session.commit()
            return True
        else:
            return False
        
    @property
    def is_admin(self):
        """
        Returns True is user has an admin role, False otherwise.
        """
        return self.has_role("admin")
        
    def reset_api_token(self):
        """Resets the users API token and returns the new value.
        """
        self.api_token = generate_api_token()
        db.session.commit()
        return self.api_token
        
    def reset_password(self):
        """Resets the user password. Returns new value.
        """
        new_password = random_password()
        self.password = current_app.user_manager.hash_password(new_password)
        db.session.commit()
        return new_password
        
class Worker(db.Model):
    __tablename__="workers"
    id = db.Column(db.Integer(), primary_key=True)
    uuid = db.Column(UUID, index=True)
    created = db.Column(db.DateTime(), nullable=False, default=datetime.datetime.now)
    updated = db.Column(db.DateTime(), nullable=True, index=True)
    
    def __repr__(self):
        return "<Worker %s>"%(str(self.uuid))
        
    def __init__(self, worker_uuid):
        self.uuid = worker_uuid
        
    def ping(self):
        """
        Register a ping event on this worker. Update the ping time.        
        """
        self.updated = datetime.datetime.now()
        
    @property
    def name(self):
        return str(self.uuid)[0:6]
        
    @property
    def lastping(self):
        """
        Return the number of seconds since the last ping.
        """
        delta = datetime.datetime.now() - self.updated
        seconds = delta.seconds+(delta.days*24*3600)
        return seconds
        
    @property
    def updated_short(self):
        return self.updated.strftime('%Y-%m-%d %H:%M:%S')
        
    @property
    def created_short(self):
        return self.created.strftime('%Y-%m-%d %H:%M:%S')
        

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

