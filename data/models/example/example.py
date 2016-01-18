from gem.model import *

class Model(GemModel):
    """
        This is an example model which shows all the configuration settings
        for the virtual globe.
    """
    meta={
        #
        # Metadata
        #
        'name':                 'example',
        'author':               'Koko Alberti',
        'contact':              'kokoalberti@fastmail.nl',
        'abstract':             'This is an example model which shows all the configuration settings for the virtual globe. It is also useful as a starting point for building your own models.',
        'license':              'All Rights Reserved',
        'tags':			 ['example','test'],
        'discretization':       'world_onedegree_100m',
        'maxchunks':            1
    }
    parameters={
        #
        # These are default params that will be overwritten by params
        # specified in the web application
        #
        'param_float':          12.323,
        'param_int':            5,
        'param_string':         'a string parameter'
    }
    time={
        #
        # Defines the time component of the model. 
        #
        'start':                 '2014-01-01T00:00:00',
        'timesteps':             6,
        'timesteplength':        3600*24 
    }
    datasources={
        #
        # Datasources are WCS servers with coverages. They are queried
        # upon initialization and their layer names stored internally. The
        # layers names can be accessed via self.readmap(<layer_name>) and
        # the system will then read the map from the correct WCS server.
        #
        'wcs':[
            'http://turbo.geo.uu.nl/cgi-bin/mapserv?MAP=/data/projectdata/globaldata/globaldata.map'        
        ],
        'osm':{
        	'connect':"PG:dbname=osm"
        }
    }
    reporting={
        #
        # The reporting section adds metadata to model output attributes.
        # By reporting a map with self.report(<name>) and the name matches
        # keys listed below, that information will be used in the webmap.
        # If you report maps without defining them here it will not show
        # up in the web interface.
        #
        'aspect': {
            'title':        "Aspect",
            'units':        "radians",
            'info':			"Aspect indicates the direction of the slope and is shown in radians.",
            'datatype':		"Float32",
            'symbolizer':{
                'type':		"pseudocolor",
                'clamp':	True,
                'ticks':	5, #ticks only works on pseudocolor symbolizers
                'colors':	["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':	[0.0,6.5],
                'labels':	[]
            }
        },
        'grade': {
            'title':        "Slope",
            'units':        "m/m",
            'info':			"Grade of the slope expressed in meters elevation per meter distance.",
            'datatype':		"Float32",
            'symbolizer':{
                'type':		"pseudocolor",
                'clamp':	True,
                'ticks':	5, #ticks only works on pseudocolor symbolizers
                'colors':	["#006600","#FFCC00","#CC0000","#4A0000"],
                'values':	[0.0,1.5],
                'labels':	[]
            }
        },
        'globcov': {
            'title':		"Land Use Classification",
            'units':		"-",
            'info':			"Land use classification shows the type of landuse and is derived from the GlobCov dataset.",
            'datatype':		"Byte",
            'symbolizer':{
                'type':		"categorical", #categorical data must have Byte datatype!!
                'colors':	['#CC0000','#0000FF','#FFFF66','#006600'],
                'values':	[190,210,14,100],
                'labels':	["Urban","Water","Cropland","Forest"]
            }
        },
        'modis':{
            'title':		"Enhanced Vegetation Index",
            'units':		"-",
            'info':			"The enhanced vegetation index (EVI) is an alternative to NDVI and is more sensitive in high-biomass regions and in areas where soil shines through.",
            'datatype':		"Float32",
            'symbolizer':{
                'type':		"classified",
                'colors':	['#FF6600','#FDD017','#9ACD32','#688E23','#006400'],
                'values':	[-2000,2000,4000,6000,8000,12000],
                'labels':	["Wasteland","Pretty Bare","Low","Medium","Rainforest"]
            }
        },
        'landuse': {
            'title':		"OSM Land Use",
            'units':		"-",
            'info':			"Landuse based on OpenStreetMap data",
            'datatype':		"Byte",
            'symbolizer':{
                'type':		"categorical", #categorical data must have Byte datatype!!
                'colors':	['#f7f4ed','#d1e7d2','#ca7b80','#fbdd7e','#e50000','#363737','#b7c9e2','#5729ce','#0e87cc'],
                'values':	[0,1,2,3,4,5,6,7,8],
                'labels':	["Undefined","Forest","Urban","Farmland","Roads","Railways","Power (Line)","Power (Tower)","Water"]
            }
        },
    }
    def initial(self):
        logger.debug("This is a debug message")
        logger.info("This is an info message")
        logger.debug("The float parameter is: %.2f"%(self.readparam("param_float")))
        self.dem=self.readmap('srtm.elevation')
        self.modis=self.readmap('modis.ndvi.2012.002')
        
        self.landuse=nominal(0)
        
        self.forest=self.readmap('osm.landuse.forest')
        self.water=self.readmap('osm.landuse.water')
        self.urban=self.readmap('osm.landuse.urban')
        self.farmland=self.readmap('osm.landuse.farmland')
        self.motorway=self.readmap('osm.infra.motorway')
        self.primary=self.readmap('osm.infra.primary')
        self.railway=self.readmap('osm.infra.railway')
        self.powerline=self.readmap('osm.infra.powerline')
        self.powertower=self.readmap('osm.infra.powertower')
        
        self.landuse=ifthenelse(self.forest==1,1,self.landuse)
        self.landuse=ifthenelse(self.urban==1,2,self.landuse)
        self.landuse=ifthenelse(self.farmland==1,3,self.landuse)
        self.landuse=ifthenelse(self.water==1,8,self.landuse)
        self.landuse=ifthenelse(self.powerline==1,6,self.landuse)
        self.landuse=ifthenelse(self.railway==1,5,self.landuse)
        self.landuse=ifthenelse(self.primary==1,4,self.landuse)
        self.landuse=ifthenelse(self.motorway==1,4,self.landuse)
        self.landuse=ifthenelse(self.powertower==1,7,self.landuse)
        

    def dynamic(self):
        logger.debug("Hello dynamic!") 
        self.report(self.landuse,"landuse")
        self.aspect=aspect(self.dem)
        self.report(self.aspect,"aspect")
        
        
        self.modis=self.modis*0.75
        self.report(self.modis,"modis")
        self.report(self.dem,"dem")
        self.report(self.readmap('globcov.2009'),'globcov')
        
        self.grade = slope(self.dem)
        self.report(self.grade,"grade")

    def postdynamic(self):
        logger.debug("Hello postdynamic!")

        

