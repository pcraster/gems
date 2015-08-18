
import os
import sys
import numpy as np
import subprocess
import json
import glob
import logging

from time import time as now
from osgeo import gdal
from osgeo import gdal_array
from osgeo import gdalconst


sys.path.append("/home/koko/pcraster/pcraster-4.0.2_x86-64/python")
from pcraster import readmap, pcr2numpy

logger=logging.getLogger()

class ModelReporter(object):
    def __init__(self):
        """
        Initialize some variables that we need for the reporting of map layers.
        """
        self._report_maps=[]
        self._report_layers={}
        self._packaging_progress=0
        
    def _report(self,data,identifier,timestamp):
        """
        Report function to store a map
        """
        if identifier in self.reporting:
            logger.debug("Reporting map '%s' (datatype:%s timestep:%d timestamp:%s timestamplocal:%s)"%(identifier,self.reporting[identifier]["datatype"],self.timestep,self.timestamp,self.timestamplocal))
            data=pcr2numpy(data,-9999)
            #
            #Todo: implement some kind of clamp functionality here. if 'clamp' is set to true 
            #      on the symbolizer for this output attribute, set all values
            #      above the max to the max value, and all below the min to the 
            #      min value. Allow overriding this in the model's report function like:
            #     report(data,'map',clamp=True) and then use pcraster/numpy to clamp the data.
            #
            (rows,cols)=data.shape
            if identifier not in list(self._report_layers):
                self._report_layers.update({identifier:[]})
            self._report_layers[identifier].append((data,timestamp))
            
            return True
        else:
            logger.error("Don't know how to report '%s', please specify in the 'reporting' section of your model configuration."%(identifier))
            return False
        
    def _report_postprocess(self):
        """
        This is called at the end of the model run and is meant for
        consolidating all the reported data and writing it to an output
        file for example, or for additional postprocessing like reprojection
        to a web mercator projection or something.
        
        Todo:
        - reproject to pseudomercator (compressed, tiled)
        - add overviews
        - create a vrt file for each timestep
        - create maps.csv file which can be used to fill the mapindex
             <config>,<attribute>,<time>,<vrt_file>
        """
        

        logger.debug("Start postprocessing of the data created by this model run")
        driver=gdal.GetDriverByName("GTiff")
        
        #the configuration key. unique for every model-config combination
        config_key=self.config.get("config_key","unknown_config_key")
        
        #the uuid of the chunk for which this model is run
        uuid_chunk=self.config.get("uuid_chunk","unknown_chunk_uuid")
        
        #the uuid of this individual model run (ie. jobchunk) this is different
        #every time, even if the config and the chunk are exactly the same.
        uuid_jobchunk=self.config.get("uuid_jobchunk","unknown_jobchunk_uuid")
        
        #create the working directory
        base_directory=self.config.get("directory")
        directory=os.path.join(self.config.get("directory"),config_key[0:2],config_key[2:4],config_key,uuid_chunk[0:2],uuid_chunk[2:4],uuid_chunk)
        if not os.path.isdir(directory):        
            os.makedirs(directory)
            
        logger.debug("Saving reported output layers to disk")
        num_of_outputs=len(list(self._report_layers))
        for i,name in enumerate(list(self._report_layers)):
            self.status()
            self._packaging_progress=float(i)/float(num_of_outputs)
            logger.debug("Packaging progress: %.2f"%(self._packaging_progress))
            time_total=now()
            #create a directory to store these layers in
            layer_directory=os.path.join(directory,name)
            if not os.path.isdir(layer_directory):        
                os.makedirs(layer_directory)
            layer_file=os.path.join(layer_directory,name)
            
            layers=self._report_layers[name]
            #options=['PHOTOMETRIC=MINISBLACK','COMPRESS=DEFLATE','TILED=YES','ZLEVEL=1']
            options=[]
            #datatype=gdal_array.NumericTypeCodeToGDALTypeCode(layers[0][0].dtype)
            

            datatype=gdalconst.GDT_Float32
            if self.reporting[name]["datatype"]=="Byte":
                datatype=gdalconst.GDT_Byte
            if self.reporting[name]["datatype"]=="Int32":
                datatype=gdalconst.GDT_Int32
            datatype_name=gdal.GetDataTypeName(datatype)

            logger.debug("Storing attribute '%s' (%d layers/timesteps) as a %s geotiff"%(name,len(layers),datatype_name))
                
            ds=driver.Create(layer_file+".tmp.tif", self._grid['cols'], self._grid['rows'], len(layers), datatype, options)
            for band_index,(data,timestamp) in enumerate(layers,start=1):
                band=ds.GetRasterBand(band_index)
                band.WriteArray(data)
                band.SetNoDataValue(-9999)
                band.SetRasterColorInterpretation(1) #Set ColorInterp to gray on all bands
                
            ds.SetGeoTransform(self._grid["geotransform"])
            ds.SetProjection(self._grid["projection"])
            ds = None
            
            #gdalwarp -overwrite -srcnodata -9999 -dstnodata -9999 -t_srs "epsg:3857" -co "COMPRESS=DEFLATE" -co "ZLEVEL=1" -co "TILED=YES" dem.tif dem.tif
            
            logger.debug("Warping to web mercator, add tiling, add compression using gdalwarp")
            time_start=now()
            c=[
                "/usr/bin/gdalwarp", "-q", "-overwrite", 
                "-srcnodata", "-9999",
                "-dstnodata", "-9999",
                "-t_srs", "epsg:3857",
                "-co", "COMPRESS=DEFLATE",
                "-co", "ZLEVEL=1",
                "-co", "TILED=YES",
                layer_file+".tmp.tif", layer_file+".tif"
            ]
            rc=subprocess.call(c)
            logger.debug("Command: %s"%(" ".join(c)))
            logger.debug("Returned status code %d. Took %.2fs"%(rc,now()-time_start))

            
            logger.debug("Adding overviews using gdaladdo")
            time_start=now()            
            c=["/usr/bin/gdaladdo","-q",layer_file+".tif","2","4","8","16","32","64","128"]
            rc=subprocess.call(c)
            logger.debug("Command: %s"%(" ".join(c)))
            logger.debug("Returned status code %d. Took %.2fs"%(rc,now()-time_start))
            
            #revisit the bands and create the virtual datasets with an embedded time step
            logger.debug("Creating virtual datasets (.vrt) for each timestep")
            time_start=now() 
            for band_index,(data,timestamp) in enumerate(layers,start=1):
                timestamp=timestamp.strftime("%Y%m%d%H%M%S")
                vrt_file=os.path.join(layer_directory,"%s-%s.vrt"%(name,timestamp))
                vrt_file_relative_path=os.path.relpath(vrt_file,base_directory)
                c=["/usr/bin/gdal_translate","-q","-co","TILED=YES","-of","VRT","-b",str(band_index),layer_file+".tif",vrt_file]
                rc=subprocess.call(c)
            
                self._report_maps.append({
                    'filename':vrt_file_relative_path,
                    'datatype':datatype_name,
                    'attribute':name,
                    'timestamp':timestamp,
                    'config_key':config_key,
                    'chunk_uuid':uuid_chunk
                })
                #remove temporary files
                tempfiles=glob.glob(os.path.join(layer_directory)+"/*tmp.tif*")
                for f in tempfiles:
                    subprocess.call(["/bin/rm",f])
            logger.debug("Creating vrt files took %.2fs"%(now()-time_start))
            logger.debug("Total time taken to report the '%s' attribute: %.2fs"%(name,now()-time_total))
        

        #create a manifest file which lists all the created map files (the .vrt
        #ones) along with their timestamp and attribute. when the maps package
        #gets uploaded to the server this file is used to insert all the 
        #entries into the 'map' table, from where  they can then be found 
        #by mapserver for displaying as tiles in the web application.
        time_start=now()
        logger.debug("Creating manifest file with %d map layers in it."%(len(self._report_maps)))
        maps_list=os.path.join(base_directory,"manifest.json")
        with open(maps_list,'w') as f:
            f.write(json.dumps(self._report_maps))  

        #create a tar archive package for publication. this is not compressed 
        #because the tif files already have compression, so that wouldn't 
        #result in any significant gains and just add overhead to the processing
        #and network transfers.
        logger.debug("Archiving model results into maps package using tar")
            
        maps_package=os.path.join(base_directory,"results-jobchunk-%s.tar"%(uuid_jobchunk))
        logger.debug("Maps package file: %s"%(maps_package))
        c=[
            "/bin/tar","-cf", maps_package, "-C", base_directory, config_key[0:2], "manifest.json"
        ]
        rc=subprocess.call(c)
        logger.debug("Command: %s"%(" ".join(c)))
        logger.debug("Returned status code %d"%(rc))
        logger.debug("Creating tar file with manifest took %.2fs"%(now()-time_start))

            
        return maps_package