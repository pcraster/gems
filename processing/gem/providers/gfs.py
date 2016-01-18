"""

The GFS provider supplies data from the global forecast system to models 
models running in the virtual globe.

Upon intialization the gfs provider:

- makes a list of start times of the gfs model runs
- goes down the list to check the start times
- find the most recent run
- 

"""

import os
import sys
import logging
import provider
import datetime
import pytz

import numpy as np

from owslib.wcs import WebCoverageService
from urlparse import urlparse, parse_qs

from osgeo import gdal, gdalconst

from shapely.geometry import box

sys.path.append("/home/koko/pcraster/pcraster-4.0.2_x86-64/python")
logger=logging.getLogger()

def round_datetime(dt=datetime.datetime.now(), seconds=-3600):
    """
    Rounds a timestamp object up or down a number of seconds. Used by 
    parsetime()
    """
    seconds_base = int(round((dt-dt.min).total_seconds()))
    return dt.min+datetime.timedelta(seconds=round_to(seconds_base,seconds))
    
def round_to(number,roundto):
    """
    Rounds an integer up or down by another integer. Used by round_datetime()
    """
    return ((number//abs(roundto))*abs(roundto))+max(0,roundto)

class GfsProvider(provider.Provider):
    def __init__(self, config, grid):
        #
        # Initialize the provider. This sets up a temporary directory and some
        # general stuff that all providers need.
        #
        provider.Provider.__init__(self, config, grid)
        
        #
        # First figure out which GFS forecast has been most recently uploaded.
        #
        gfs_layers=[]
        self.gfs_wcs_access_urls={}
        gfs_dt=[]
        start = round_datetime(dt=datetime.datetime.utcnow(), seconds=-21600)
        
        logger.debug("Looking for most recent GFS dataset")
        for offset in xrange(-21600*1, -21600*6, -21600):
            logger.debug("trying date")
            gfs_latest = start + datetime.timedelta(seconds=offset)
            gfs_dt.append(gfs_latest)      
            logger.debug("create date")
            wcs_url=gfs_latest.strftime("http://nomads.ncdc.noaa.gov/thredds/wcs/gfs-004/%Y%m/%Y%m%d/gfs_4_%Y%m%d_%H%M_000.grb2")
            try:
                logger.debug("Trying WCS at %s"%(wcs_url))
                wcs = WebCoverageService(wcs_url, version='1.0.0')
                logger.debug("Fine...")
            except:
                logger.debug("Exception! Continue to next loop!!")
                continue
            logger.debug("moving on...")
            logger.debug("Connected to GFS WCS at %s"%(wcs_url))
            contents = list(wcs.contents)
            if len(contents) > 0:
                for layer in contents:
                    gfs_layers.append(layer)
                    
                    self.available_layers.append(layer)
                    
                for hours in xrange(0,300,3):
                    timestamp = gfs_latest + datetime.timedelta(hours=hours)
                    timestamp = timestamp.replace(tzinfo=pytz.utc)
                    hr = "%.3d"%(hours)
                    wcs_access_url = gfs_latest.strftime("http://nomads.ncdc.noaa.gov/thredds/wcs/gfs-004/%Y%m/%Y%m%d/gfs_4_%Y%m%d_%H%M_"+hr+".grb2")
                    cache_key = gfs_latest.strftime("gfsrun-%Y%m%d%H%M-"+hr+"-")
                    self.gfs_wcs_access_urls.update({timestamp.isoformat():{'url':wcs_access_url,'cache_key':cache_key}})
                    
                self.gfs_run_timestamp = gfs_latest
                break
            else:
                continue
            
        logger.debug("The following GFS WCS urls will be used for timesteps:")
        for k in sorted(self.gfs_wcs_access_urls):
            logger.debug("Timestamp: %s WCS URL: %s"%(k,self.gfs_wcs_access_urls[k]))
        
    def provide(self,name,options={}):
        """
        
        Return a numpy array of the requested data
        
        todo:
        - split into a download() or get_from_cache()
        
        """
        logger.debug("Looking for layer '%s' at timestamp '%s'"%(name,options['timestamp']))        
        if name not in self.available_layers:
            logger.error("Layer '%s' is not available in this provider."%(name))
        if options['timestamp'].isoformat() not in self.gfs_wcs_access_urls:
            logger.error("Timestamp %s was not found in the list of available GFS timesteps."%(options['timestamp'].isoformat()))
        
        logger.debug("Downloading coverage from url:")
        logger.debug(self.gfs_wcs_access_urls.get(options['timestamp'].isoformat()))
        
        extent=box(*self._grid["bounds"]).buffer(1.0)
        logger.debug("request bounds: %s"%(str(extent.bounds)))      
        
        
        req_url=self.gfs_wcs_access_urls[options['timestamp'].isoformat()]['url']
        cache_key=self.gfs_wcs_access_urls[options['timestamp'].isoformat()]['cache_key']+name
        logger.debug("req_url=%s"%(req_url))
        
        wcs=WebCoverageService(req_url, version='1.0.0')
        meta=wcs.contents[name]
            
        #cov = wcs.getCoverage(identifier=name,bbox=extent.bounds, format="GeoTIFF_Float")
        try:
            cov = wcs.getCoverage(identifier=name, bbox=extent.bounds, format="GeoTIFF_Float")
            filename=os.path.join(self._cache,"%s.tif"%(cache_key))
            logger.debug("WCS: saving file to: %s"%(filename))
            with open(filename,'w') as f:
                f.write(cov.read())
            dataset = gdal.Open(filename, gdalconst.GA_ReadOnly)
        except Exception as e:
            logger.error("WCS: failure: %s"%(e))
        
        return self.warp_to_grid(dataset)
        #pass

