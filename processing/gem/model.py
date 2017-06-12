import psycopg2
import psycopg2.extras
import sys
import os
import requests
import json
import beanstalkc
import datetime
import logging
import pytz
import random
import ast

#from tzwhere import tzwhere
#tz = tzwhere.tzwhere()

from osgeo import gdal, ogr, osr, gdalconst
from pcraster import *
from pcraster.framework import *
from providers import get_provider_by_name
from reporting import ModelReporter
from shapely.geometry import box

#workaround because pcraster also imports max, min, time functions and 
#thereby overwrites python's builtin ones :/ we use time for general timing
#of how long a model run takes, so it's not really crucial.
from __builtin__ import max as max_ 
from time import time as now_

#fetch a logger instance
logger=logging.getLogger()

class GemModel(DynamicModel, ModelReporter):
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
        
    # @property
    # def timestamplocal(self):
    #     """
    #     Returns a datetime object for the current model time in local time at 
    #     the centroid of this model chunk.
    #     """
    #     if self._timezone is not None:
    #         local_dt = self.timestamp.astimezone(self._timezone)
    #         return self._timezone.normalize(local_dt)
    #     else:
    #         return None
        

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
    
    def status(self, force=False):
        """
        Sends a status update to the API. There is a maximum limit of one 
        update every two seconds so as not to overload the API with status
        updates which are not so relevant. This behaviour can be bypassed by
        passing the force=True argument, forcing the update regardless of 
        how long it's been since the last update. This is useful for key 
        moments in the model run, like the start or the end of processing.
        """
        try:
            now = now_()
            time_since_last_update = (now-getattr(self,"_last_status_update",0))
            percent_done = self.percent_done
            if (time_since_last_update > 2.0) or (force==True):
                logger.debug("Status update accepted: %d percent complete."%(percent_done))
                self._last_status_update = now
                url = self._api+"/job/chunk/"+self._job["uuid_jobchunk"]
                r = requests.post(url,data={'status_percentdone':percent_done})
                r.raise_for_status()
        except:
            logger.debug("Status update to the api at %s failed."%(self._api))
        else:
            logger.debug("Status update to the api: %d percent done."%(percent_done))
        finally:
            return percent_done
        
    def setConfig(self, config):
        logger.debug("Setting configuration:")
        logger.debug("  - The configuration key for this run is: %s"%(config["config_key"]))
        self.config = config
        
    def setParameters(self, parameters):
        """
        Overwrite the parameters property of the model with the
        parameters received from the message queue. The "update" of
        the parameters dict has already occurred at this point as that
        takes place when the job is created by the API.
        """
        logger.debug("Setting model parameters:")
        self.parameters.update(parameters)
        for param in sorted(parameters):
            logger.debug("  - (%s) %s -> %s"%(str(type(parameters[param])),param,parameters[param]))

    def setGrid(self, grid):
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
          
        Todo:
        
        * Rasterization to create a boolean mask should use a timer in case
          gdal.RasterizeLayer freezes.
          
        """
        self._grid = grid
        
        logger.debug("Creating the modelling grid on a UTM projection:")
        logger.debug(" - Rows: %d"%(grid['rows']))
        logger.debug(" - Columns: %d"%(grid['cols']))
        logger.debug(" - Bounding box (utm): %s"%(str(grid['bbox_utm'])))
        logger.debug(" - Bounding box (latlng): %s"%(str(grid['bbox_latlng'])))
        

        if len(grid['mask']) > 1024:
            logger.debug(" - WKT mask: %s"%(str(grid['mask'])))
        else:
            logger.debug(" - WKT mask: %s (...) Rest of geojson mask omitted for brevity."%(str(grid['mask'])[0:256]))
        

        try:
            logger.debug("Setting the PCRaster clone map:")
            logger.debug(" - Parameters used: nrRows=%d nrCols=%d cellSize=%d west=%f north=%f"%(grid["rows"],grid["cols"],grid["cellsize"],1.212,1.223))
            setclone(grid["rows"],grid["cols"],grid["cellsize"],1.212,1.223)
        except Exception as e:
            logger.critical(" - setclone operation failed! (%s)"%(e))
            raise Exception(e)
        else:
            logger.debug(" - setclone Completed.")
        
        try:
            logger.debug("Creating a raster mask for this chunk from the GeoJSON mask defined in the job:")
            srs = osr.SpatialReference()  
            srs.ImportFromWkt(self._grid["projection"])  
            drv = ogr.GetDriverByName("ESRI Shapefile")
            filename = "/vsimem/temp-chunk-%s.shp"%(random.random())
            ds = drv.CreateDataSource(filename)
            #ds = drv.CreateDataSource("/tmp/temp-shape.shp")
            logger.debug("Created in memory shapefile data source: %s"%(filename))
            layer = ds.CreateLayer("feature_layer", geom_type=ogr.wkbPolygon, srs=srs)   
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetGeometry(ogr.CreateGeometryFromWkt(str(grid['mask'])))
            layer.CreateFeature(feature)
                        
            #Create a GDAL raster datasource representative of the chunk
            self._mask = gdal.GetDriverByName('MEM').Create('', self._grid['cols'], self._grid['rows'], 1, gdalconst.GDT_Float32)
            self._mask.SetGeoTransform(self._grid["geotransform"])
            self._mask.SetProjection(self._grid["projection"])
            
            
            logger.debug("Calling gdal.RasterizeLayer()")
            err = gdal.RasterizeLayer(self._mask, (1,), layer, burn_values=(1,), options=["ALL_TOUCHED=TRUE"])
            logger.debug("Done!")
            if err != 0:
                raise Exception("Rasterization failed with error code %d"%(err))
            else:
                mask = self._mask.GetRasterBand(1).ReadAsArray()
                self._mask = numpy2pcr(Boolean, mask, 0) 
                #calculate how much percent of the grid is covered by the mask. a value
                #of 100% here means you have a rectangular mask probably
                mask_coverage = int(100 * ( maptotal(scalar(self._mask)) / maptotal(scalar(spatial(boolean(1)))) ) )
        except Exception as e:
            logger.debug(" - Rasterization of mask failed! Using a full mask on the entire grid instead. Hint: %s"%(e))
            self._mask = spatial(boolean(1))
            mask_coverage = 100
        else:
            logger.debug(" - Rasterization of mask succeeded.")
        finally:
            logger.debug(" - Rasterized mask for this chunk covers %d pct of the chunk grid."%(mask_coverage))
            ds = None

    def setTime(self):
        logger.debug("Setting model time:")
        try:
            self._epoch=datetime.datetime.strptime(self.parameters["__start__"],"%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.utc)
            logger.debug(" - UTC start time of the model to: %s"%(self._epoch.isoformat()))
        except:
            logging.critical(" - Could not establish a starting datetime for this model run. The __time__ parameter passed was: %s"%(userModel.parameters.get("__time__","(empty)")))
            raise Exception("Could not establish a starting datetime for this model run.")
            
        ##
        ## Determining timezones is very problematic, ignore this for now... All model time must be in UTC
        ##
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
        #self._timezone = None
        #logging.debug("The (approximate) timezone of this model run is: %s"%(str(self._timezone)))
        #logging.debug("You can access the 'timestamplocal' property on this model instance to get the current model time converted to local time.")

    def setProviders(self, datasources):
        """
        Configure each of the dataproviders found in the datasources 
        section of the model.
        """
        self._providers = {}
        self._layers = {}
        for name,config in datasources.items():
            logger.debug("Loading data provider: %s"%(name))
            try:
                prov = get_provider_by_name(name, config, self._grid)
            except Exception as e:
                logger.debug(" - Failed to load %s provider."%(name))
                logger.debug(" - Error: %s"%(e))
                logger.debug(" - Skipping %s"%(name))
            else:
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
                logger.debug(" - The '%s' provider serves %d data layers: %s"%(name,len(prov.available_layers)," ".join(prov.available_layers)))
        logger.debug("Loaded %d data providers."%(len(self._providers)))
    
    def setJob(self,job):
        self._job = job

    def setAPI(self,gems_api):
        self._api = gems_api

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

    def readparam(self, param):
        if param in list(self.parameters):
            return self.parameters[param]
        else:
            return None

    def setMaps(self, maps):
        self._maps=maps

    def report(self, data, identifier):
        """
        Report a variable. 

        The variable self._reporter should contain a reporter for this
        model. If it exists, report the map there with a set of kwargs
        consisting of the timestamp, attribute, datatype, and data field.
        The reporter takes care of the rest.

        """
        self._report(data, identifier, self.timestamp)
        
    def lookup(self, table=""):
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
    
    def lookupdict(self, classmap, string, defaultval=-9999):
        """
        Python method for reclassifying a map using a Python dictionary. 
        The method will take a string that is given through the parameters 
        section and turn it into a python dictionary. The 'type' key of the 
        dictionary will determine whether the resulting map will be ordinal,
        nominal, scalar, boolean or ldd. 
        """
        lookup = ast.literal_eval(string)
        maptype = lookup.get('maptype', 'scalar')
        resmap = scalar(defaultval)

                
        for key in lookup.keys():
            if isinstance(key, float) or isinstance(key, int):
                inval = float(key)
                valuemap = scalar(lookup.get(key))
                valuemask = ifthen(pcreq(scalar(classmap), inval), valuemap)
                resmap = cover(valuemask, resmap)
        
        if maptype is 'nominal':
            resmap = pcraster.nominal(resmap)
        elif maptype is 'ordinal':
            resmap = pcraster.ordinal(resmap)
        elif maptype is 'boolean':
            resmap = pcraster.boolean(resmap)
        elif maptype is 'ldd':
            resmap = pcraster.ldd(resmap)
        else:
            resmap = pcraster.scalar(resmap)
                
        return resmap