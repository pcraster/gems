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

from pcraster import readmap, pcr2numpy, ifthenelse

logger=logging.getLogger()

class ModelReporter(object):
    def __init__(self):
        """
        Initialize some variables that we need for the reporting of map layers.
        """
        self._report_maps = []
        self._report_layers = {}
        self._packaging_progress  =0
        
    def _report(self, data, identifier, timestamp):
        """
        Report function to store an attribue maps. In the traditional PCRaster 
        the report function writes a map straight to a location on disk, with
        a directory structure and filename which is representative of the attribute
        and timestep at which the reporting takes place. This can cause some 
        problems thougg. For example, a model reports 8 attributes, and the model
        has 24 timesteps. This will result in 192 map files, each of which (due to the
        PCRaster file format) is uncompressed, does not have detailed georeference
        information, does not contain overviews for quick zooming out, and is in 
        the wrong projection (that of the model, rather than web mercator that we
        need).

        In GEMS we choose a slightly different approach and use GeoTiff as the 
        storage mechanism. The variable self._report_layers contains the model 
        outputs and has the following structure:

        {
            '<attribute_name>' : [ (<data_array>, <utc_timestamp>), (...), (...) ]
        }

        This way, accessing self._report_layers['snow_depth'] will return an array
        of tuples, of which each tuple contains a numpy array and a timestamp.

        To get a list of the reported attributes we can simply use list(self._report_layers)

        Every time an attribute is reported it is added to this variable, and 
        at the end of the model run the _report_postprocess() is called, which turns
        each reported attribute into a separate geotiff file where the bands in
        the geotiff file correspond to one of the timesteps. Performing operations
        on these stacked geotiffs (such as creating overviews, requesting subsections,
        slices, or reprojecting) is much more efficient than on separate files.
        """
        try:
            if identifier in self.reporting:
                logger.debug("Reporting map '%s' (datatype:%s timestep:%d timestamp:%s)"%(identifier, self.reporting[identifier]["datatype"], self.timestep, self.timestamp))
                # Crop by the mask. Set all data outside mask to nodata value
                data = ifthenelse(self._mask, data, -9999)            
                # Convert to numpy array. The numpy array will be added to stack
                # of maps, one for each timestep.
                data = pcr2numpy(data, -9999)
                #
                #Todo: implement some kind of clamp functionality here. if 'clamp' is set to true 
                #      on the symbolizer for this output attribute, set all values
                #      above the max to the max value, and all below the min to the 
                #      min value. Allow overriding this in the model's report function like:
                #      report(data,'map', clamp=True) and then use pcraster/numpy to clamp the data.
                #
                (rows,cols) = data.shape
                if identifier not in list(self._report_layers):
                    self._report_layers.update({identifier:[]})
                self._report_layers[identifier].append((data, timestamp))
            else:
                logger.error("Don't know how to report '%s', please specify in the 'reporting' section of your model configuration."%(identifier))
        except:
            logger.error("An exception occurred while trying to report '%s'"%(identifier))
            return False
        else:
            logger.debug(" - Reporting map '%s' completed."%(identifier))
            return True

    def _report_postprocess(self):
        """
        The reporting postprocess method is called at the end of the model run, and
        assembles the attribute maps reported into the self._report_layers attribute 
        throughout the model run into a single highly optimized "maps package" which
        is then posted back to the API. This maps package contains all the model's 
        output maps. Furthermore, it creates .vrt (virtual datasets) which reference
        'slices' of the geotiff files, one for each timestep. We do this because 
        mapserver can't index the time component on a certain band (i.e. time x
        corresponds to band n of file.tif). 

        Using these vrt files we can make a nice tileindex in mapserver with a 
        time field in the database and a filelocation field which points to the 
        vrt file. All the while our raster maps are still stored as geotiffs, so 
        they profit from all the advantages (reprojected, overviews, tiling, 
        compression, etc.) 

        So, here we, for each attribute map:
            - Stack the timesteps into a single GeoTiff
            - Warp to web mercator projection
            - Compress with deflate algorithm on fastest mode
            - Add overviews
            - Add tiling
            - Create a vrt file for each timestep

        Then for all the maps together:
            - Create a manifest.json file which contains an entry for each file for 
              the postgis/mapserver tile index.
            - Package all the files into a single tar file (uncompressed, as the
              rasters themselves are already compressed)
            - This "maps package" is the finished result of the model run, and can
              be posted to the API. 
            
        Notes and todos:
            - Investigate if it's possible to further optimize this by using the 
              gdal libraries in python, rather than using subprocess to call the
              gdal executables directly.

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
            
            logger.debug("Warping to [?], add tiling, add compression using gdalwarp")
            time_start=now()
            c=[
                "/usr/bin/gdalwarp", "-q", "-overwrite", 
                "-srcnodata", "-9999",
                "-dstnodata", "-9999",
                #"-t_srs", "epsg:4326",
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
                    'chunk_uuid':uuid_chunk,
                    'filesrs':"epsg:%d"%(self._grid["srid"])
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
