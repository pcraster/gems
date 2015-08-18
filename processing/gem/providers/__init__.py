
def get_provider_by_name(name, config, grid):
    """
        Get a provider by name. The config and the grid variable are needed by
        providers to supply the data they need to. The grid variable is a dict
        like:
        
        {
            'discretization': u'world_onedegree_100m', 
            'uuid': '53637e06-29b5-43e3-8e62-d5e22876d6bc', 
            'bounds': (175.0, -42.0, 176.0, -41.0), 
            'geotransform': (), 
            'cellsize': 100, 
            'bbox': (331792.1148057926, 5348288.940567572, 417181.9307515907, 5460761.410625033), 
            'srid': 32760,
            'rows':1115,
            'cols':854
        }
        
        This tells the provider the geographical extent and the grid size that
        it wants the data for. The provider may under no circumstances give 
        back something else! The 'uuid' entry is the uuid of the job that this
        run belongs to.
        
        The 'config' variable can be anything that this provider needs to do
        its job properly. It is configured in the model and has a datastructure
        which depends on how the provider works. For example, for the wcs
        provider it needs to be provided with URLs of wcs servers which it can
        then query. This is configured in the model's 'datasources' section.
        
        The type of data that should be supplied should be documented in each
        of the provider classes.
        
        For more hints on making a new provider see the summy provider in the
        file example.py.
        
        
        ---------------
        
        Notes:

        Some ideas:

        wcs -> get data from a wcs layer
        wfs -> rasterize maps from a wfs
        postgres -> rasterize shapes from a postgres databas
        forecast -> get data from a forecast
        osm->rasterize osm layers
        wkt -> make a raster based on wkt points which can come from input params.

        ideas for rasterizing shapes:
        http://pcjericks.github.io/py-gdalogr-cookbook/raster_layers.html
        
        
        ------------------
    """
    if name.lower() == 'wcs':
        from . import wcs
        return wcs.WcsProvider(config,grid)
        
    elif name.lower() == 'gfs':
        from . import gfs
        return gfs.GfsProvider(config,grid)

    elif name.lower() == 'osm':
        from . import osm
        return osm.OsmProvider(config,grid)

    elif name.lower() == 'example':
        from . import example
        return example.ExampleProvider(config,grid)
        
    elif name.lower() == 'wfs':
        from . import wfs
        return wfs.WfsProvider(config,grid)
                
    elif name.lower() == 'postgis':
        from . import postgis
        return postgis.PostGISProvider(config,grid)

    elif name.lower() == 'wkt':
        from . import wkt
        return wkt.WKTProvider(config,grid)        
        
    else:
        raise Exception("Provider not found: %s"%(name))
  

