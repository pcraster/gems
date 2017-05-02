"""
Provider for serving OSM data through a PostGIS connection.
"""

import os
import sys
import logging
import provider
import numpy as np
from osgeo import gdal, gdalconst, ogr

sys.path.append("/opt/pcraster/python")
logger=logging.getLogger()

class OsmProvider(provider.Provider):
    def __init__(self, config, grid):
        #
        # Initialize the provider. This sets up a temporary directory and some
        # general stuff that all providers need.
        #
        provider.Provider.__init__(self, config, grid)
        
        #
        # The OSM provider lets you request rasterized layers from the OSM
        # dataset. A data layer is defined by the queries below. Mixing and 
        # matching these layers (for example to make a landuse map) should
        # be done in the model itself. This is because there is a possibility
        # that the layers overlap: a motorway pixel can also be occupied by 
        # a railway or a water body. How you deal with this should be defined
        # in the model itself.
        #
        self.osm_layers = {
            'osm.landuse.urban':{
                'query':    "select ST_Transform(way,4326) from planet_osm_polygon where planet_osm_polygon.landuse='residential' or planet_osm_polygon.landuse='retail' or planet_osm_polygon.landuse='railway' or planet_osm_polygon.landuse='industrial' or planet_osm_polygon.landuse='greenhouse_horticulture' or planet_osm_polygon.landuse='commercial' or planet_osm_polygon.amenity!=''",
                'options':  ["ALL_TOUCHED=TRUE"]
            },
            'osm.landuse.farmland':{
                'query':    "select ST_Transform(way,4326) from planet_osm_polygon where planet_osm_polygon.landuse='farmland' or planet_osm_polygon.landuse='farmyard'",
                'options':  ["ALL_TOUCHED=TRUE"]
            },
            'osm.landuse.water': {
                'query':    "select ST_Transform(way,4326) from planet_osm_polygon where planet_osm_polygon.waterway!='' or planet_osm_polygon.natural='water'"
            },
            'osm.landuse.forest': {
                'query':    "select ST_Transform(way,4326) from planet_osm_polygon where planet_osm_polygon.landuse='forest'"
            },
            'osm.infra.motorway': {
                'query':    "select ST_Transform(way,4326) from planet_osm_roads where planet_osm_roads.highway='motorway' or planet_osm_roads.highway='trunk'"
            },
            'osm.infra.primary': {
                'query':    "select ST_Transform(way,4326) from planet_osm_roads where planet_osm_roads.highway='primary'"
            },
            'osm.infra.secondary': {
                'query':    "select ST_Transform(way,4326) from planet_osm_roads where planet_osm_roads.highway='secondary'"
            },
            'osm.infra.railway': {
                'query':    "select ST_Transform(way,4326) from planet_osm_roads where planet_osm_roads.railway='rail'"
            },
            'osm.infra.powerline': {
                'query':    "select ST_Transform(way,4326) from planet_osm_line where planet_osm_line.power='line'"
            },
            'osm.infra.powertower': {
                'query':    "select ST_Transform(way,4326) from planet_osm_point where planet_osm_point.power='tower'"
            }
        }
        #
        # Define some default options for GdalRasterize
        #        
        self.default_rasterize_options = ["ALL_TOUCHED=TRUE"]
        
        #
        # Add the layers to the list of this providers' available layers. This
        # way the model knows what layers are available.
        #
        for layer in list(self.osm_layers):
            self.available_layers.append(layer)

    def provide(self, name, options={}):
        """        
        Return a numpy array of the requested data        
        """
        logger.debug("OSM provider is looking for layer '%s'..."%(name))    
        
        # Create an in memory dataset with the current grid on it. This will be
#        # used to burn the shapes into.
#        dst = gdal.GetDriverByName('GTiff').Create('MEM', self._grid['cols'], self._grid['rows'], 1, gdalconst.GDT_Byte)
#        dst.SetGeoTransform(self._grid["geotransform"])
#        dst.SetProjection(self._grid["projection"])
#        
        dst = self.create_clone(datatype = gdalconst.GDT_Byte, initvalue = 0)
        
        src = ogr.Open("PG:dbname=osm", 0)
        if src is None:
            logger.error("Could not open postgis datasource for OSM data")
        else:
            query = self.osm_layers[name].get('query',None)
            if query is None:
                logger.error("No query for layer '%s' could be found in the osm provider's configuration."%(name))
            else:
                layer = src.ExecuteSQL(query)
                featureCount = layer.GetFeatureCount()
                if featureCount < 1:
                    logger.error("No features were found within the specified bounding box.")
                else:
                    rasterize_options = self.osm_layers[name].get('options',self.default_rasterize_options)
                    err = gdal.RasterizeLayer(dst, (1,), layer, burn_values=(1,), options=rasterize_options)
                    if err != 0:
                        logger.error("Rasterization operation failed! Hint: %s"%(err))
        
        # Finally return the numpy array of this band. If part of the operation
        # failed (no features, error while rasterizing, no query defined) an 
        # error will be logged and the empty raster with zeros will be returned.
        band = dst.GetRasterBand(1)
        dt = np.dtype(np.float32)
        if gdal.GetDataTypeName(band.DataType) in ('Int32','Int16','Byte'):
            dt = np.dtype(np.int32)
        data = np.array(band.ReadAsArray(), dtype=dt)

        return data
