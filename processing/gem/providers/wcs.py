import os
import sys
import logging
import provider
import pyproj
import numpy as np

from owslib.wcs import WebCoverageService
from urlparse import urlparse, parse_qs
from osgeo import gdal, gdalconst
from functools import partial


from shapely.wkt import loads
from shapely.ops import transform


logger=logging.getLogger()

class WcsProvider(provider.Provider):
    """Documentation WCS provider.


    """
    def __init__(self, config, grid):
        """
        Initialization code for this specific provider. First initialize the
        base provider and then to some custom setup stuff specific to the
        wcs provider.

        The provider needs to update the self.available_layers attribute and
        append all the layers that it can provide to this attribute. Since
        a provider can literally provide any sort of layer and any number of
        them, this cannot be done automatically, and therefore must be done
        explicitly in the provider's __init__.
        """
        provider.Provider.__init__(self, config, grid)

        try:
            self._layers = {}
            for wcs_url in config:
                wcs = WebCoverageService(wcs_url, version='1.0.0')
                contents = list(wcs.contents)
                for layer in contents:
                    self.available_layers.append(layer)
                    #make a mapping in the _layers variable about which wcs url
                    #we need to query to fetch a particular layer
                    self._layers.update({layer:wcs_url})
        except:
            logger.debug(" - %s provider couldn't find any layers to make available.")

    def provide(self, name, options={}):
        """
        The providers' provide() method returns a numpy with the
        correct data type and propotions given the layer name and
        possibly some extra options. The readmap() in the model
        will convert the numpy array to a pcraster map when it is
        requested.
        """
        logging.debug("WCS: provide request for layer '%s'"%(name))
        target_file = os.path.join(self._cache,"%s"%(name))
        crs = None
        srid = None
        dataset = None
        logging.debug("WCS: geometry: %s"%(self._geom.wkt))
        url = urlparse(self._layers[name])
        qs = parse_qs(url.query)
        query_params={}
        for p in list(qs):
            query_params.update({p:qs[p][0]})

        wcs = WebCoverageService(url.geturl(), version='1.0.0')
        meta = wcs.contents[name]
        mapformat = meta.supportedFormats[0]
        supported_crses = [crs_.code for crs_ in meta.supportedCRS]
        logging.debug("WCS: Service supports the following crs: %s"%(", ".join(map(str,supported_crses))))

        if self._grid['srid'] in supported_crses:
            crs = meta.supportedCRS[supported_crses.index(self._grid['srid'])]
            srid = self._grid['srid']
        elif 4326 in supported_crses:
            crs = meta.supportedCRS[supported_crses.index(4326)]
            srid = 4326
        else:
            crs = meta.supportedCRS[supported_crses.index(supported_crses[0])]
            srid = supported_crses[0]

        if crs is not None and srid is not None:
            logging.debug("WCS: using %s (epsg:%d) to fetch the file from the wcs server"%(crs,srid))
        else:
            logging.debug("WCS: could not agree upon a projection format to fetch data with")
            raise Exception("WCS: no valid projections found")

        logging.debug("WCS: reprojecting the chunk mask to the required projection")

        project = partial(pyproj.transform, pyproj.Proj(init="epsg:%d"%(self._grid['srid'])), pyproj.Proj(init="epsg:%d"%(srid)))

        #Add a small buffer to the request so we fetch an area slightly larger
        #than what we really need. This will prevent some edge effects due
        #to the reprojection.
        projected_geom = transform(project,self._geom.buffer(200))

        logging.debug("WCS: original geom: %s"%(self._geom.wkt))
        logging.debug("WCS: reprojected geom: %s"%(projected_geom.wkt))

        try:
            logging.debug("WCS: fetching wcs data in %s"%(crs))
            logging.debug("WCS: saving to: %s"%(target_file+".tif"))
            cov = wcs.getCoverage(identifier=name, crs=crs, bbox=projected_geom.bounds, format=mapformat, width=self._grid['cols'], height=self._grid['rows'], **query_params)
            with open(target_file+".tif",'w') as f:
                f.write(cov.read())
            dataset = gdal.Open(target_file+".tif",gdalconst.GA_ReadOnly)
        except Exception as e:
            logger.error("WCS: failure: %s"%(e))


        utm_data = self.warp_to_grid(dataset)
        dataset = None
        return utm_data
