
#import yaml
#import subprocess
import psycopg2
import psycopg2.extras
import sys
import os
import requests
import json
import beanstalkc
import datetime
import logging


from shapely.geometry import box

sys.path.append("/home/koko/pcraster/pcraster-4.0.2_x86-64/python")
logger=logging.getLogger()

logger.debug("Loading timezone information, please wait...")
import pytz

#from tzwhere import tzwhere
#tz = tzwhere.tzwhere()

logger.debug("Loading pcraster and the modelling framework...")
from pcraster import *
from pcraster.framework import *

from providers import get_provider_by_name
from reporting import ModelReporter


from osgeo import gdal, gdalconst, ogr, osr

#workaround because pcraster also imports max, min, time functions and 
#thereby overwrites python's builtin ones :/ we use time for general timing
#of how long a model run takes, so it's not really crucial.
from __builtin__ import max as max_ 
from time import time as now_

class GemModel(DynamicModel,ModelReporter):
    def __init__(self):
        #dynamicmodel provides the methods for modelling
        DynamicModel.__init__(self)
        #reporter provides methods for reporting data
        ModelReporter.__init__(self)

    @property
    def elapsed(self):
        """
        Returns the number of seconds that have elapsed in model time since
        the start of the run.
        """
        seconds_to_add=(self.timestep-1)*self.timesteplength
        return max_(0,seconds_to_add) #in case self.timestep is negative, seconds_to_add will also be.

    @property
    def timestep(self):
        """
        Returns the current timestep.
        """
        return self.currentStep
        
    @property
    def timesteplength(self):
        """
        Returns the length of one timestep in seconds. Could be called
        timestepdelta or something as well.
        """
        return self.time["timesteplength"]
        
    @property
    def timestamp(self):
        """
        Returnss a datetime object for the location of the current model. Will
        default to the start time at timestep <= 1.
        """
        return (self._epoch + datetime.timedelta(seconds=self.elapsed))
        
    @property
    def timestamplocal(self):
        """
        Returns a datetime object for the current model time in local time at 
        the centroid of this model chunk.
        """
        if self._timezone is not None:
            local_dt = self.timestamp.astimezone(self._timezone)
            return self._timezone.normalize(local_dt)
        else:
            return None
        

    @property
    def percent_done(self):
        """
        Makes an educated guess at how far done the model is depending on
        the self._phase attribute. Its a little bit impossible to estimate
        the true progress, as timesteps may be processed quickly and then 
        the model takes a long time writing and reprojecting outfiles. It 
        could be the opposite too, a very slow and complicated model run
        which only outputs a few maps. We just don't know... so instead we
        make some educated guesses which most appropriately give the user
        an idea of how much work remains to be done.
        
         "prepare"          5%
         "initial"          10%       can take longer because of loading data from data providers
         "dynamic"          10-60%    depending on the timestep
         "packaging"        60-90%    takes longer because data needs to be reported, reprojected, and posted to the API as map package
         "complete"         95%       just need to upload and unpack the maps package
         
         100% completion is not done by the model but set by the api once the map 
         package has been received and processed.
        """
        if hasattr(self,"_phase"):
            logging.debug("Phase is: %s"%(self._phase))
            if self._phase=="prepare":
                return 5
            if self._phase=="initial":
                return 10
            if self._phase=="dynamic":
                perc=float(self.timestep)/float(self.time["timesteps"])
                return 10+int(perc*50)
            if self._phase=="postdynamic":
                return 60
            if self._phase=="packaging":
                return 60+int(self._packaging_progress*35)
            if self._phase=="complete":
                return 95
        else:
            return 0
    
    def status(self,force=False):
        """
        Sends a status update to the API. There is a maximum limit of one 
        update every two seconds so as not to overload the API with status
        updates which are not so relevant. This behaviour can be bypassed by
        passing the force=True argument, forcing the update regardless of 
        how long it's been since the last update. This is useful for key 
        moments in the model run, like the start or the end of processing.
        """
        now=now_()
        time_since_last_update=(now-getattr(self,"_last_status_update",0))
        percent_done=self.percent_done
        if (time_since_last_update > 2.0) or (force==True):
            logger.debug("Status update accepted: %d percent complete."%(percent_done))
            self._last_status_update=now
            url=self._job["api_url"]+"/job/chunk/"+self._job["uuid_jobchunk"]+"/status"
            r=requests.post(url,data={
                'status_percentdone':percent_done            
            })
        else:
            logger.debug("Status update rejected at %d percent done."%(percent_done))
        return percent_done
        
    def setConfig(self,config):
        logger.debug("Setting configuration:")
        self.config=config
        logger.debug("  The configuration key for this run is: %s"%(config["config_key"]))
        
    def setParameters(self,parameters):
        """
        Overwrite the parameters property of the model with the
        parameters received from the message queue. The "update" of
        the parameters dict has already occurred at this point as that
        takes place when the job is created by the API.
        """
        logger.debug("Setting parameters:")
        self.parameters.update(parameters)
        for param in sorted(parameters):
            logger.debug("  %s -> %s"%(param,parameters[param]))

    def setGrid(self,grid):
        """
        Sets the model grid that this model will be run on. Several things
        happen here:
        
        - Dynamically set the pcraster clone map by calling setclone() with
          the required rows and columns.
          
        - Create an in-memory shapefile with a single feature: the polygon
          of the particular chunk this model is run for.
          
        - Rasterize this in memory shapefile to create a raster mask for
          this run. This allows model runs in oddly shaped chunks such as 
          river catchments, provinces, or other shapes which are not 
          rectanguler. This mask is stored in the self._mask variable. If
          something goes wrong at this step the mask is set to equal the
          grid. During reporting the self._mask variable is used to crop
          any output layers along the mask. It is important that self._mask
          is always set!
          
        """
        self._grid = grid
        
        logger.debug("Setting the modelling grid on a UTM projection:")
        logger.debug(" - Rows: %d"%(grid['rows']))
        logger.debug(" - Columns: %d"%(grid['cols']))
        logger.debug(" - Bounding box (projected): %s"%(str(grid['bbox'])))
        logger.debug(" - Bounding box (lat-lng): %s"%(str(grid['bounds'])))
        logger.debug(" - Geojson mask: %s"%(str(grid['mask'])))
        
        logger.debug("Setting the pcraster clone map dynamically with the following params:")
        logger.debug("   nrRows=%d nrCols=%d cellSize=%d west=%f north=%f"%(grid["rows"],grid["cols"],grid["cellsize"],1.212,1.223))
        
        setclone(grid["rows"],grid["cols"],grid["cellsize"],1.212,1.223)
        
        logger.debug("Trying to create the mask for this chunk.")
        try:
            drv = ogr.GetDriverByName("ESRI Shapefile")
            ds = drv.CreateDataSource("/vsimem/temp.shp")
            layer = ds.CreateLayer("feature_layer", geom_type = ogr.wkbPolygon)    
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetGeometry(ogr.CreateGeometryFromWkt(str(grid['mask'])))
            layer.CreateFeature(feature)

            self._mask = gdal.GetDriverByName('MEM').Create('', self._grid['cols'], self._grid['rows'], 1, gdalconst.GDT_Float32)
            self._mask.SetGeoTransform(self._grid["geotransform"])
            self._mask.SetProjection(self._grid["projection"])
            err = gdal.RasterizeLayer(self._mask, (1,), layer, burn_values=(1,), options=["ALL_TOUCHED=TRUE"])
            if err != 0:
                raise Exception("Rasterization failed with error code %d"%(err))
            else:
                logger.debug("Rasterization of mask succeeded.")
                mask = self._mask.GetRasterBand(1).ReadAsArray()
                self._mask = numpy2pcr(Boolean, mask, 0)  
        except Exception as e:
            logger.debug("Rasterization of the mask failed! Hint: %s"%(e))
            self._mask = boolean(1)
        finally:
            ds = None

    def setTime(self):
        try:
            self._epoch=datetime.datetime.strptime(self.parameters["__start__"],"%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.utc)
            logger.debug("Setting the UTC start time of the model to: %s"%(self._epoch.isoformat()))
        except:
            logging.critical("Could not establish a starting datetime for this model run. The __time__ parameter passed was: %s"%(userModel.parameters.get("__time__","(empty)")))
            raise Exception("Could not establish a starting datetime for this model run.")
            
        #logging.debug("Calculating centroid...")
        #centroid = box(*self._grid['bounds']).centroid
        #logging.debug("Establishing timezone for chunk's centroid location: x=%.3f y=%.3f"%(centroid.x,centroid.y))
        #try:
         #   tzone = tz.tzNameAt(centroid.y,centroid.x)
         #   logging.debug("Found timezone:")
          #  logging.debug(tzone)
           # self._timezone = pytz.timezone(tzone)
        #except:
        #    logging.debug("A timezone could not be found for this chunk centroid. It is most likely near or in the ocean, for which timezones cannot be reliably calculated.")
        #    self._timezone = None
        self._timezone = None
        logging.debug("The (approximate) timezone of this model run is: %s"%(str(self._timezone)))
        logging.debug("You can access the 'timestamplocal' property on this model instance to get the current model time converted to local time.")

    def setProviders(self,datasources):
        logger.debug("Setting data providers:")
        self._providers={}
        self._layers={}
        #
        # Configure each of the dataproviders found in the datasources 
        # section of the model.
        #
        for name,config in datasources.items():
            logger.debug("Loading data provider: %s"%(name))
            try:
                prov=get_provider_by_name(name,config,self._grid)
                logger.debug("The '%s' provider serves %d data layers: %s"%(name,len(prov.available_layers)," ".join(prov.available_layers)))

                # for this model we must keep track of which provider is responsible
                # for which layer, so what when 'srtm.elevation' is requested we know
                # to ask the wcs provider for it, and when 'forecast.temperature' is
                # requested we know to ask the forecastio provider for it. The data
                # is stored in the self._layers dict.
                for layer in prov.available_layers:
                    self._layers.update({layer:name})
                
                # store the provider instance in the model's self._providers dict,
                # it can be accessed via self._providers[<name>]
                self._providers.update({name:prov})
            except Exception as e:
                logger.error("Loading the '%s' provider raised an exception. Hint: %s"%(name,e))
    
    def setJob(self,job):
        self._job=job

    def readmap(self,name,options={}):
        """
        Request data from one of the providers. This first checks if/which 
        provider has registered the requested layer, and then calls the 
        request_map function of the correct provider to supply the model with
        the requested data.
        
        The options argument can contain optional extras that the provider
        might need to do its job. The current time is added as default. It is 
        the providers responsibility to return either a numpy array or pcraster
        field object with the right dimensions.
        """
        if name in self._layers:
            options.update({'timestamp':self.timestamp})
            provider = self._providers[self._layers[name]]
            data = provider.provide(name,options)
            if (data.shape != (self._grid["rows"],self._grid["cols"])):
                logger.error("Number of cols and cols does not match the model grid!")
                return None
            else:
                if str(data.dtype)=='int32':
                    return numpy2pcr(Nominal,data,-9999)
                else:
                    return numpy2pcr(Scalar,data,-9999)
        else:
            logger.error("Layer '%s' was not found in the list of layers provided by the data providers."%(name))
            return None

    def readparam(self,param):
        if param in list(self.parameters):
            return self.parameters[param]
        else:
            return None

    def setMaps(self,maps):
        self._maps=maps

    def setClone(self,clone="clone"):
        """
        Set the clone map of the model. This function is called by
        the framework.
        """
        logger.debug("SKIPPING regular setclone operation. Clone map is now set dynamically in setGrid()")
#        clone_file=self.readmap("clone",return_what="filename")
#        try:
#            logger.debug("Set clone map to file: %s"%(clone_file))
#            setclone(clone_file)
#            clone_metadata=self.readmap("clone",return_what="metadata")
#            #print " * Found metadata on clone file:"
#            self._clone_metadata=clone_metadata
#        except Exception as e:
#            logger.error("Failed to set a clone map!")


    def report(self,data,identifier):
        """
        Report a variable. 

        The variable self._reporter should contain a reporter for this
        model. If it exists, report the map there with a set of kwargs
        consisting of the timestamp, attribute, datatype, and data field.
        The reporter takes care of the rest.

        """
        self._report(data,identifier,self.timestamp)
        
    def lookup(self,table=""):
        """
        Do some form of pcraster table lookup. In the desktop pcraster we need to 
        pass a filename, but no such thing exists in the virtual globe, so 
        instead allow the passing of a string with a table in it. Write that
        to a temporary file, and then do the right lookupscalar() or other
        lookup function on the file, and return the map. Maybe its even 
        possible to use another format for this... sometime like:
        
        lookupjson(self,json_string)
        
        And that the json object will contain the info needed to do a lookup/
        conversion/reclassification.
        
        Todo: make a decision on how to deal with this in the best way.
        """
        pass        



