import sys
import os
import numpy as np
import logging

from osgeo import gdal, gdalconst
from pcraster import readmap

from shapely.wkt import loads

logger = logging.getLogger()

class Provider(object):
    """
    Base class for a GEMS data provider. All providers must extend this 
    class and implement their own provide() method which provides the 
    layer that the model is requesting. See the example.py provider for
    some ideas.

    The provider base provides functionality that all providers share, 
    as well as some additional convenience methods that allow providers
    to easily reproject a grid onto the model grid (e.g. warp_to_grid).
    """
    def __init__(self, config, grid):
        # Initialize some properties that all the providers have in common
        # and may want to utilize for their own purposes.
        logger.debug(" - Initializing '%s'"%(self.__class__.__name__))

        # Set some attributes
        self._config = config
        self._grid = grid
        self._name = self.__class__.__name__
        self.available_layers = []
        
        #
        # Create an empty gdal dataset to use as a target for any warping.
        # This empty dataset matches the cell size and extent of the raster
        # grid that we're running on.
        #
        logger.debug(" - Creating an empty map as a template for this provider")
        self._clone = self.create_clone()

        #self._clone = gdal.GetDriverByName('MEM').Create('', self._grid['cols'], self._grid['rows'], 1, gdalconst.GDT_Float32)
        #self._clone.SetGeoTransform(self._grid["geotransform"])
        #self._clone.SetProjection(self._grid["projection"])
        
        
        try:
            self._geom = loads(self._grid["mask"])
        except:
            self._geom = None
                
        
        # Create a caching directory which is unique for this provider and 
        # this chunk uuid. The provider can use this directory to do extra
        # computations in and to store cached files which have been requested
        # previously. This way a second run in the same area doesn't need to
        # download the data all over again.

        # TODO:::: maybe get rid of this.... caching is a bit of a premature optimization at this point...
        try:
            self._cache = os.path.join('/tmp/', "gems-provider-data", self._name, self._grid['uuid'], "cache")
            if not os.path.isdir(self._cache):        
                os.makedirs(self._cache) #create the cache directory
        except:
            raise Exception("Creating cache directory %s for provider %s failed!"%(self._cache, self._name))
        else:
            logger.debug(" - Cache directory for %s provider: %s"%(self._name, self._cache))
        
    def provide(self, name, options={}):
        """
        The provide method of a provider must return a numpy array of the 
        dimensions specified in the self._grid dict to the model. How it does
        this, or what datatype it makes this array is completely up to the 
        provider to decide.
        """
        raise NotImplementedError()
    
    def create_clone(self, datatype=gdalconst.GDT_Float32, nodatavalue=None, initvalue=None):
        """
        Return an in memory one band dataset which matches the projection and 
        cellsize required for this particular chunk/run. The provider can then 
        do its thing on this blank canvas, whether it is rasterizing shapes,
        reprojecting other data, downloading some figures, or drawing something 
        else.
        """
        clone = gdal.GetDriverByName('MEM').Create('', self._grid['cols'], self._grid['rows'], 1, datatype)
        clone.SetGeoTransform(self._grid["geotransform"])
        clone.SetProjection(self._grid["projection"])

        if nodatavalue is not None:
            clone.GetRasterBand(1).SetNoDataValue(nodatavalue)
        
        if initvalue is not None:
            clone.GetRasterBand(1).Fill(initvalue)
        
        return clone
    
    def warp_to_grid(self, dataset, resample=gdalconst.GRA_NearestNeighbour):
        """
        Return the provided GDAL dataset, but reprojected onto a model grid,
        matching the target pixel size, resolution, etc. This method can be 
        used by all providers that obtain their data in a different projection
        (for exampe the GFS provier which obtains a geotiff in lat-lng and
        needs to provide data to the model in a UTM projection).
        """
        dst = self.create_clone()
        
        logger.debug("Warping a dataset to the model grid")
        logger.debug("Input: %s"%(dataset.GetProjection()))        
        logger.debug("To: %s"%(dst.GetProjection()))
        
        gdal.ReprojectImage(dataset, dst, dataset.GetProjection(), dst.GetProjection(), resample)
        band = dst.GetRasterBand(1)
        
        dt = np.dtype(np.float32)
        if gdal.GetDataTypeName(band.DataType) in ('Int32','Int16','Byte'):
            dt = np.dtype(np.int32)

        data = np.array(band.ReadAsArray(), dtype=dt)
        dataset = None
        dst = None

        return data

    def burn_to_grid(self, dataset, options):
        """
        Burns the features in an ogr dataset into a raster given the options
        passed as an argument. This is used by various vector providers such
        as the OsmProvider and WfsProvider.
        
        Dataset may be either a string pointing to a file on the disk, or a 
        gdal dataset object.
        """
        pass
            
    def has_layer(self,layername):
        """
        Checks if this provider is making available a layer with the provided
        name.
        """
        if layername in self.available_layers:
            return True
        else:
            return False