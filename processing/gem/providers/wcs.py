"""

WCS provider for the virtual globe.

Todo:
- use provider.warp_to_grid to reproject any data not available in the 
  correct projection/coordinate system.

"""

import os
import sys
import logging
import provider

import numpy as np

from owslib.wcs import WebCoverageService
from urlparse import urlparse, parse_qs

from osgeo import gdal, gdalconst

sys.path.append("/home/koko/pcraster/pcraster-4.0.2_x86-64/python")
logger=logging.getLogger()

class WcsProvider(provider.Provider):
    def __init__(self, config, grid):
        #
        # Initialize the provider. This sets up a temporary directory and some
        # general stuff that all providers need.
        #
        provider.Provider.__init__(self, config, grid)
        
        #
        # Set up stuff specific for this provider
        #        
        self._layers = {}
        for wcs_url in config:
            wcs=WebCoverageService(wcs_url, version='1.0.0')
            contents=list(wcs.contents)
            for layer in contents:
                self.available_layers.append(layer)
                #make a mapping in the _layers variable about which wcs url 
                #we need to query to fetch a particular layer
                self._layers.update({layer:wcs_url})
                
#    def valid_layer(self,name):
#        if name in self._layers:
#            return True
#        else:
#            return False
#    
#    def request_map(self,name):
#        try:
#            target_file=self.request_filename(name)
#            return readmap(target_file.encode('utf-8'))
#        except Exception as e:
#            print " * File could not be read! Hint:%s"%(e)
#
#    def request_filename(self,name,file_format='map'):
#        if self.valid_layer(name):
#            target_file=os.path.join(self._cache,"%s.%s"%(name,file_format))
#            #if not os.path.isfile(target_file):
#            self.fetch(name)
#            return target_file
#            
#    def request_metadata(self,name):
#        """
#        return metadata for a layer
#        """      
#        try:
#            target_file=self.request_filename(name,file_format="tif")
#            dataset=gdal.Open(target_file,GA_ReadOnly)
#            return {
#                'rows':dataset.RasterYSize,
#                'cols':dataset.RasterXSize,
#                'bands':dataset.RasterCount,
#                'projection':dataset.GetProjection(),
#                'geotransform':dataset.GetGeoTransform()
#            }
#        except Exception as e:
#            print " * File could not be read! Hint:%s"%(e)

    def provide(self,name,options={}):
        """
        
        Return a numpy array of the requested data
        
        todo:
        - split into a download() or get_from_cache()
        
        """
        
        
        target_file=os.path.join(self._cache,"%s"%(name))
        
        
        url=urlparse(self._layers[name])
        qs=parse_qs(url.query)
        query_params={}
        for p in list(qs):
            query_params.update({p:qs[p][0]})

        print "Creating a coverage url:"
        print url.geturl()
        wcs=WebCoverageService(url.geturl(), version='1.0.0')
        meta=wcs.contents[name]

        mapformat=meta.supportedFormats[0]
        
        supported_crses=[crs.code for crs in meta.supportedCRS]            
        
        try:
            crs=meta.supportedCRS[supported_crses.index(self._grid['srid'])]
        except ValueError:
            raise Exception("WCS provider could not retrieve layer '%s' because it is not available in the UTM grid that the model needs to run at. We need a raster in epsg %d, available are only epsg %s. The wcs provider does not do reprojection/warping itself."%(name,self._grid['srid']," ".join(map(str,supported_crses))))

        resx=self._grid['cellsize']
        resy=self._grid['cellsize']
        bbox=self._grid['bbox']
        cov=wcs.getCoverage(identifier=name,crs=crs,bbox=bbox,format=mapformat,resx=resx,resy=resy,**query_params)
        
        #Dict used for converting geotiffs to pcraster format. Any data
        #types not set explicitly will become Float32/VS_SCALARS
        #pcraster_valuescale = defaultdict(lambda: ('Float32','VS_SCALAR'))
        #pcraster_valuescale.update({
        #    'Float32':  ('Float32','VS_SCALAR'),
        #    'Int32':    ('Int32','VS_NOMINAL'),
        #    'Int16':    ('Int32','VS_NOMINAL'), 
        #    'Byte':     ('Int32','VS_NOMINAL')
        #})
        #logger.debug( " * Downloading %s"%(cov.url))
        
        with open(target_file+".tif",'w') as f:
            f.write(cov.read())

        dataset = gdal.Open(target_file+".tif",gdalconst.GA_ReadOnly)
        band = dataset.GetRasterBand(1)

        
        dt=np.dtype(np.float32)
        if gdal.GetDataTypeName(band.DataType) in ('Int32','Int16','Byte'):
            dt=np.dtype(np.int32)

        data = np.array(band.ReadAsArray(),dtype=dt)
        band = None        
        dataset = None
        return data
        
#        try:
#            #-of PCRaster -co "PCRASTER_VALUESCALE=VS_SCALAR" -ot Float32 -a_nodata 500.1
#            c=[
#                '/usr/bin/gdal_translate','-q',
#                '-ot',pcraster_type[0],
#                '-of','PCRaster',
#                '-co','PCRASTER_VALUESCALE=%s'%(pcraster_type[1]),
#                target_file+".tif",target_file+".map"
#            ]
#            print "Conversion command: "
#            print " ".join(c)
#            rc=subprocess.call(c)
#        except Exception as e:
#            print " * Conversion to pcraster format failed!!! Hint: %s"%(e)
#        print " * Completed!"


#    @property
#    def layers(self):
#        """
#        For external use when we just want a list of layres from
#        this provider. The provider is responsible for fetching
#        the right one when .request() is called, so the outside
#        world doesnt care about the actual urls.
#        """
#        return list(self._layers)
