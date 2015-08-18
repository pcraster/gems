import sys
import os
sys.path.append("/home/koko/pcraster/pcraster-4.0.2_x86-64/python")
from pcraster import readmap
import numpy as np
import logging
from osgeo import gdal, gdalconst
logger=logging.getLogger()

class Provider(object):
    """
    Base class for a data provider in the virtual globe. 
    
    Implement some form of caching for the providers.
    """
    def __init__(self, config, grid):
        
        # Initialize some properties that all the providers have in common
        # and may want to utilize for their own purposes.
        logger.debug("Initializing provider '%s'"%(self.__class__.__name__))
        self._config = config
        self._grid = grid
        self._name = self.__class__.__name__
        
        #
        # Create an empty gdal dataset to use as a target for any warping.
        # This empty dataset matches the cell size and extent of the raster
        # grid that we're running on.
        #
        logger.debug("Creating an empty gridded dataset")
        self._clone = gdal.GetDriverByName('MEM').Create('', self._grid['cols'], self._grid['rows'], 1, gdalconst.GDT_Float32)
        self._clone.SetGeoTransform(self._grid["geotransform"])
        self._clone.SetProjection(self._grid["projection"])
        
        
        # Create a caching directory which is unique for this provider and 
        # this chunk uuid. The provider can use this directory to do extra
        # computations in and to store cached files which have been requested
        # previously. This way a second run in the same area doesn't need to
        # download the data all over again.
        logger.debug("Creating cache directory...")
        self._cache = os.path.join(os.environ.get('DIGITALEARTH_RUNDIR'), "provider-data", self._name, self._grid['uuid'], "cache")
        if not os.path.isdir(self._cache):        
            os.makedirs(self._cache) #create the cache directory
        logger.debug("Cache directory: %s"%(self._cache))
    
        #
        # Stored the names of available layers
        #    
        self.available_layers = []

            
    def layers(self):
        """
        Returns a list of layer names that this provider offers.
        """
        return []
        
    def readmap(self):
        """
        Reads a map from this provider
        """
        return "This is a map"
        
    def provide(self,name,options={}):
        """
        The provide method of a provider must return a numpy array of the 
        dimensions specified in the self._grid dict to the model. How it does
        this, or what datatype it makes this array is completely up to the 
        provider to decide.
        
        """
        pass
    
    def create_clone(self, datatype = gdalconst.GDT_Float32, nodatavalue=None, initvalue=None):
        """
        Returns an in memory raster map which matches the projection and cell
        size required for this particular chunk/run. The provider can then 
        do its thing on this blank canvas, whether it is rasterizing shapes,
        reprojecting other data, or drawing something else.
        """
        clone = gdal.GetDriverByName('MEM').Create('', self._grid['cols'], self._grid['rows'], 1, datatype)
        clone.SetGeoTransform(self._grid["geotransform"])
        clone.SetProjection(self._grid["projection"])

        if nodatavalue is not None:
            clone.GetRasterBand(1).SetNoDataValue(nodatavalue)
        
        if initvalue is not None:
            clone.GetRasterBand(1).Fill(initvalue)
        
        return clone
    
    def warp_to_grid(self, dataset):
        """
        Takes any georeferenced geotiff input file (or gdal dataset) and uses GDAL to reproject
        it onto the grid of the model run, matching the target pixel size, 
        resolution, etc. This method can be used by providers which somehow
        get their data in a different projection (for example the gfs 
        provider which obtains a geotiff in latlng and needs to provide the
        data to the model on the correct utm grid.)
        
        Dataset may be either a string pointing to a file on the disk, or a 
        gdal dataset object.
        """
        src = gdal.Open(dataset, gdalconst.GA_ReadOnly)
        
#        dst = gdal.GetDriverByName('GTiff').Create('MEM', self._grid['cols'], self._grid['rows'], 1, gdalconst.GDT_Float32)
#        dst.SetGeoTransform(self._grid["geotransform"])
#        dst.SetProjection(self._grid["projection"])
        
        dst = self.create_clone()
        
        gdal.ReprojectImage(src, dst, src.GetProjection(), dst.GetProjection(), gdalconst.GRA_NearestNeighbour)
        band = dst.GetRasterBand(1)
        
        dt = np.dtype(np.float32)
        if gdal.GetDataTypeName(band.DataType) in ('Int32','Int16','Byte'):
            dt = np.dtype(np.int32)

        data = np.array(band.ReadAsArray(), dtype=dt)
        src = None        
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