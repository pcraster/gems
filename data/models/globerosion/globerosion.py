from gem.model import *

import time as time_
from math import e as const_e

class Model(GemModel):
    """
        Model description here
    """
    meta={
        #
        # Metadata
        #
        'name':                 'globerosion',
        'author':               'Koko Alberti',
        'contact':              'kokoalberti@fastmail.nl',
        'abstract':             'Estimates monthly soil erosion estimates using a RUSLE in monthly timesteps. Uses global soil, elevation, climate, and vegetation data based on MODIS imagery from 2012.',
        'license':              '',
        'tags':                 ['erosion','rusle','land degradation'],
        'discretization':       'world_onedegree_100m'
    }
    parameters={
        #
        # These are default params that will be overwritten by params
        # specified in the web application
        #
        'slopelength':          50.0,
        'lapserate':            0.2,
        'test':                    10.0,
        'test2':                4
    }
    time={
        'start':                 '2014-01-15T00:00:00',
        'timesteps':             12,
        'timesteplength':        3600*24*30 #30 day timesteps
    }
    datasources={
        #
        # Datasources are WCS servers with coverages. They are queried
        # upon initialization and their layer names stored internally. The
        # layers names can be accessed via self.readmap(<layer_name>) and
        # the system will then read the map from the correct WCS server.
        #
        # The readmap function has access to the model time, so it is
        # possible that the data provider may return something different
        # when it is called on the same layer in the next timestep. The 
        # WCS provider doesnt do this (i.e. you need to request layer worldclim.precip.005\
        # for the data in May, but the forecastio provider does to this (ie
        # requesting forecast.temperature will use the model time in the API
        # request and return a new value for each timestep.
        #
        'wcs':[
            'http://turbo.geo.uu.nl/cgi-bin/mapserv?MAP=/data/projectdata/globaldata/globaldata.map'        
        ],
        'forecastio':[
            'api_key'
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
        'soilloss': {
            'title':        "Monthly soil loss",
            'units':        "t/ha",
            'info':            "Estimated monthly soil losses in tons per hectare per month.",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ["#008000","#FFFF00","#FF0000"], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [0.0,5.0],
                'labels':    []
            }
        },
        'soillosstotal': {
            'title':        "Cumulative soil loss test",
            'units':        "t/ha",
            'info':            "Estimated monthly cumulative soil losses in tons per hectare",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "classified",
                'clamp':    True,
                'colors':    ["#008000","#FFFF00","#FFA500","#FF0000"], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [0.0,5.0,10.0,20.0,50.0],
                'labels':    ["Slight","Moderate","High","Severe"]
            }
        },
        'kfactor': {
            'title':        "Soil erodibility factor",
            'units':        "-",
            'info':         "Soil erodibility factor K",
            'datatype':     "Float32",
            'symbolizer':{
                'type':     "pseudocolor",
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'clamp':    True,
                'colors':   ["#006600","#FFCC00","#CC0000"],
                'values':   [0.0,0.5],
                'labels':   []
            }
        },
        'lsfactor': {
            'title':        "Slope length factor",
            'units':        "-",
            'info':         "Slope length factor LS",
            'datatype':     "Float32",
            'symbolizer':{
                'type':     "pseudocolor",
                'clamp':     True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':   ["#006600","#FFCC00","#CC0000"],
                'values':   [0.0,10.0],
                'labels':   []
            }
        },
        'rfactor': {
            'title':        "Monthly rainfall erosivity",
            'units':        "-",
            'info':         "Monthly rainfall erosivity factor.",
            'datatype':     "Float32",
            'symbolizer':{
                'type':     "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':   ["#92DEFC","#2A27E8","#62066A"],
                'values':   [0.0,4.0],
                'labels':   []
            }
        },
        'cfactor': {
            'title':        "Monthly crop cover",
            'units':        "-",
            'info':         "Monthly crop cover protection factor derived from MODIS imagery. Defines to what extent the soil is protected against splash erosion. A lower value means better protection.",
            'datatype':     "Float32",
            'symbolizer':{
                'type':     "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':   ["#006400","#6B8E23","#9ACD32","#FFD700"],
                'values':   [0.0,1.0],
                'labels':   []
            }
        }
    }
    def initial(self):
        print "Hello, initial"
        print "The slope length for this run is: %.2f"%(self.readparam("slopelength"))
        
        
        self.alpha=scalar(-2.0)
        self.beta=scalar(1.0)
        self.b0=scalar(36.85)
        self.b1=scalar(1.09)
        self.zero=boolean(0)
        self.one=boolean(1)
        self.slopelength=scalar(20.0*3.28)
        
        self.dem=self.readmap('srtm.elevation')
        self.grade=slope(self.dem)
        self.slope=atan(self.grade)
        
        self.spow=(sin(self.slope)/0.0896) / ( (3.0*sin(self.slope)**0.8)+0.56 )
        self.spow=self.spow/(1+self.spow) 
        
        self.aspect=scalar(aspect(self.dem))
        
        self.E=scalar(0.0) #variable to keep track of cumulative soil loss
        
        self.const_e=scalar(const_e)
        
        #
        # Calculate the soil erodibility factor (K)
        #
        Fclay=self.readmap("soilgrids.clay")
        Fsand=self.readmap("soilgrids.sand")
        Fsilt=self.readmap("soilgrids.silt")
        
        self.K=0.32*( (Fsilt/(Fsand+Fclay))**0.27)
        self.report(self.K,"kfactor")
        
        #
        # Calculate the slope length factor (LS)
        #
        self.L=(self.slopelength/72.6)**self.spow
        self.steep=ifthenelse(self.grade<0.09,10.8*sin(self.slope)+0.03,16.8*sin(self.slope)-0.50)
        self.LS=self.L*self.steep
        self.report(self.LS,"lsfactor")
        
        #
        # To calculate the monthly rainfall erosivity we need the annual 
        # rainfall total as well. So, calculate that first by fetching 
        # all the monthly rainfall maps here in the initial section of
        # the model. Once the worldclim maps have been loaded the first 
        # time from the WCS using self.readmap() they should be cached
        # locally.
        #
        self.annual_r=scalar(0.0)
        for timestep in range(1,13):
            monthly_r=self.readmap("worldclim.precip.%03d"%(timestep))
            self.annual_r=self.annual_r+monthly_r

    def dynamic(self):
        print "Hello dynamic!"
        #self.report(self.grade,"grade")
        #time_.sleep(0.5)
        self.status()
        
        
        #
        # Calculate the crop cover factor C using MODIS derived EVI values
        #
        # Equation based on van der Knijf et al. (2000)
        #
        evi = self.readmap("modis.evi.2012.%03d"%(self.timestep))
        evi = ifthenelse((evi/10000)<0,0,(evi/10000))
        
        self.C=exp(self.alpha*(evi/(self.beta-evi)))
        self.report(self.C,"cfactor")
        
        #
        # Calculate the monthly rainfall erosivity factor R
        #
        monthly_r = self.readmap("worldclim.precip.%03d"%(self.timestep))
        self.R = self.b0*((monthly_r/self.annual_r)**self.b1)
        self.report(self.R,"rfactor")
        
        #
        # Calculate the monthly 'soil loss' total E
        #
        monthly_e = self.R*self.K*self.LS*self.C
        self.report(monthly_e,"soilloss")
        
        self.E=self.E+monthly_e
        self.report(self.E,"soillosstotal")
        

    def postdynamic(self):
        pass
        

