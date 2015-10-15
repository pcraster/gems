# -*- coding: utf-8 -*-
import sys
import os
import requests
import datetime
import subprocess
import logging

from time import time as now

from owslib.wcs import WebCoverageService

from pcraster import *
from pcraster.framework import *

logger = logging.getLogger()

class GemFramework(DynamicFramework):
    """
    Framework class for Gem models
    """
    def __init__(self, options, gems_api="http://localhost/api/v1"):
        logger.info("Initializing the modelling framework")

        time_start = now()
        self.time_total = now()
        #this dict stores some timing information for the model which, at the
        #end of the run, is outputted to the logger. 
        self._timings={
            'total':0,
            'setup':0,
            'initial':0,
            'dynamic':0,
            'postdynamic':0,
            'providers':0,
            'packaging':0
        }        


        
        self._options={}
        self._options.update(options)
        
        uuid=self._options["uuid_jobchunk"]
        code=self._options["modelcode"]
        parameters=self._options["parameters"]
        grid=self._options["grid"]

        self._wd=os.path.join(os.getcwd(),uuid)
        if not os.path.isdir(self._wd):
            os.makedirs(self._wd)
        logger.debug("Working directory of this model run: %s"%(self._wd))

        model_file=os.path.join(self._wd,"modelcode.py")
        with open(model_file,'w') as f:
            f.write(code)
            logger.debug("Model code is in: %s"%(model_file))

        userModel=self._loadModel()

        userModel._workingdir=self._wd
        userModel._mapspackage=None
        userModel._phase="prepare"

        userModel.setAPI(gems_api)
        userModel.setParameters(parameters)
        userModel.setGrid(grid)
        userModel.setProviders(userModel.datasources)
        userModel.setJob(options)
        userModel.setTime() #must come after setParameters()

        try:
            lastTimeStep=int(userModel.time["timesteps"])
        except:
            lastTimeStep=0
        
        #Set some options that the reporter needs to write output files.
        options={
            'directory':self._wd,
            'uuid_chunk':self._options["uuid_chunk"],
            'uuid_jobchunk':self._options["uuid_jobchunk"],
            'config_key':self._options["config_key"]
        }
        #options.update(userModel._clone_metadata)
        
        userModel.setConfig(options)
        
        DynamicFramework.__init__(self, userModel, lastTimeStep, 1)
        
        self.setQuiet()
        self._timings["setup"]=now()-time_start 

    def _loadModel(self):
        """
        Loads the model
        """
        try:
            logger.debug("Attempting to load the model code:")
            sys.path.append(self._wd)
            self._module = __import__("modelcode")
            self._model = getattr(self._module,"Model")
            m = self._model()
        except Exception as e:
            logger.critical(" - An error occurred while trying to load the model: %s."%(e))
        else:
            logger.debug(" - Model code loaded successfully.")
            return m

    def _unloadModel(self):
        """
        Unloads a model
        """
        try:
            logger.debug("Attempting to unload the model code:")
            del self._module
            del sys.modules["modelcode"]
            del self._model
            sys.path.remove(self._wd)
        except Exception as e:
            logger.debug(" - Failed to unload model code.")
        else:
            logger.debug(" - Unloaded model code successfully.")
        
    def _preRun(self):
        """
        In the beginning... Collect maps that we need for this run
        """
        pass
    
    def reportstatus(self,status_code):
        pass


    def run(self):
        """
            Run the model.
        """
        try:
            
            
            
            time_start=now()
            self._userModel().status(force=True)
            self._preRun()
            self._atStartOfScript()
            self._userModel()._phase="initial"
            self._userModel().status(force=True)
            self._runInitial()
            self._timings["initial"]=now()-time_start            
            
            time_start=now()
            self._userModel()._phase="dynamic"
            self._userModel().status(force=True)
            self._runDynamic()
            self._timings["dynamic"]=now()-time_start            
            
            time_start=now()
            self._userModel()._phase="postdynamic"
            self._runPostdynamic()
            self._timings["postdynamic"]=now()-time_start            
            
            time_start=now()
            self._userModel()._phase="packaging"
            self._userModel().status(force=True)
            self._postRun()            
            self._timings["packaging"]=now()-time_start
            
            self._userModel()._phase="complete"
            self._userModel().status(force=True)
            
            self._timings["total"]=now()-self.time_total
                
        except Exception as e:
            logger.error("An exception occurred during this run! Hint: %s"%(e))
        finally:
            self._unloadModel()

    def _postRun(self):
        """
        The end... Send the results off to a server for visualiztaion
        """
        maps_package=self._userModel()._report_postprocess()
        self._mapspackage=maps_package
        
    def _runPostdynamic(self):
        self._userModel().postdynamic()


