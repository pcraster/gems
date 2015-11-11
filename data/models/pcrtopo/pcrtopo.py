from gem.model import *

class Model(GemModel):
    """
        Model description here
    """
    meta={
        #
        # Metadata
        #
        'name':                 'pcrtopo',
        'author':               'Koko Alberti',
        'contact':              'kokoalberti@fastmail.nl',
        'abstract':             'Calculates topographic derivates from the SRTM digital elevation model.',
        'license':              'All Rights Reserved',
        'tags':			 ['topography','SRTM','slope','aspect'],
        'discretizations':      ['world_onedegree_100m']
    }
    parameters={
        #
        # These are default params that will be overwritten by params
        # specified in the web application
        #
        'parameter1':            12.323,
        'lapserate':             0.2,
        'anewparameter':         0.55,
        'geomorphon_distance':   180, 
        'stringparam':           'watsditdan',
        'some_other_param':		 2.3,
        'test': 				'value'
    }
    time={
        #
        # Defines the time component of the model. 
        #
        'start':                 '2014-01-01T00:00:00',
        'timesteps':             1,
        'timesteplength':        3600 
    }
    datasources={
        #
        # Datasources are WCS servers with coverages. They are queried
        # upon initialization and their layer names stored internally. The
        # layers names can be accessed via self.readmap(<layer_name>) and
        # the system will then read the map from the correct WCS server.
        #
        'wcs':[
            'http://turbo.geo.uu.nl/cgi-bin/mapserv?MAP=/data/projectdata/globaldata/globaldata.map',
            'http://geodata.nationaalgeoregister.nl/ahn2/wcs'
        ]
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
        }
    }
    def initial(self):
        logger.debug("Hello initial!")
        logger.debug("The lapse rate for this run is: %.2f"%(self.readparam("lapserate")))
        self.dem=self.readmap('srtm.elevation')
        self.modis=self.readmap('modis.ndvi.2012.002')
        self.ahn=self.readmap('ahn2:ahn2_5m')

    def dynamic(self):
        logger.debug("Hello dynamic!")
        #self.aspect=aspect(self.dem)
        self.report(self.ahn,"elev")
        self.aspect=aspect(self.ahn)
        self.report(self.aspect,"aspect")
        
        
        self.modis=self.modis*0.75
        self.report(self.modis,"modis")
        self.report(self.dem,"dem")
        self.report(self.readmap('globcov.2009'),'globcov')
        
        self.grade = slope(self.ahn)
        self.report(self.grade,"grade")

    def postdynamic(self):
        logger.debug("Hello postdynamic!")

        

