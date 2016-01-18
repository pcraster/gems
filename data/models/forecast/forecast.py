from gem.model import *

class Model(GemModel):
    """
    Model description
    """
    meta={
        #
        # Metadata
        #
        'name':                 'forecast',
        'author':               'Koko Alberti',
        'contact':              'kokoalberti@fastmail.nl',
        'abstract':             'Cellular automata model which uses GFS forecasts',
        'license':              'All Rights Reserved',
        'tags':             ['demo','fire','forest fire','forecast','cellular automata'],
        'discretization':       'southeast_african_countries_10000m',
        'maxchunks':            1
    }
    parameters={
        #
        # These are default params that will be overwritten by params
        # specified in the web application
        #
        'fire_hazard_level':     3
    }
    time={
        #
        # Defines the time component of the model. 
        #
        'start':                 'now',     #defaults to now if this string can't be parsed as a utc datetime
        'startroundoff':         -21600,    #round down to the nearest 6h, defaults to 60 seconds
        'startoffset':             0,          #and go back three days, defaults to 0
        'timesteps':             16,
        'timesteplength':        10800 
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
        'gfs': {
            'option':'value'
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
        'temp': {
            'title':        "Temperature",
            'units':        "C",
            'info':            "Forecast temperature in degrees Celcius.",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ["#7e1e9c","#0343df","#15b01a","#fac205","#fd3c06","#e50000","#840000"],
                'values':    [-10,50.0],
                'labels':    []
            }
        },
        'grade': {
            'title':        "Slope",
            'units':        "m/m",
            'info':            "Grade of the slope expressed in meters elevation per meter distance.",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ["#006600","#FFCC00","#CC0000","#4A0000"],
                'values':    [0.0,1.5],
                'labels':    []
            }
        }
    }
    def initial(self):
        #self.dem=self.readmap('srtm.elevation')
        #self.modis=self.readmap('modis.ndvi.2012.002')
        
       
        #self.grade=slope(self.dem)
        pass
        

    def dynamic(self):
        self.status()
        #self.grade = slope(self.dem)
        #self.report(self.grade,"grade")
        self.temp=self.readmap('Temperature_surface')
        self.temp=self.temp-273.15 #convert kelvin to celcius
        self.report(self.temp,"temp")

    def postdynamic(self):
        logger.debug("Hello postdynamic!")

        

