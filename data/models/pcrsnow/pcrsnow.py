from gem.model import *

class Model(GemModel):
    """
    Add a description of the pcrsnow here.
    """
    meta={
        #
        # Metadata
        #
        'name':                 'pcrsnow',
        'author':               'GEMS',
        'contact':              '',
        'abstract':             'PCR-SNOW is a simple snowmelt model which can calculate snow accumulation and snow melt on daily timesteps.',
        'license':              '',
        'tags':                 ['snow','melt','accumulation'],
        'discretization':       'rocky_mountain_national_park_100m',
        'maxchunks':            1
    }
    parameters={
        #
        # These are default params that will be overwritten by params
        # specified in the web application.
        #
        'lapserate' :           0.007,
        'downscaling_factor':   350,
        'degreeday_melt_factor':0.01
    }
    time={
        'start':                 '2014-01-15T00:00:00',
        'timesteps':             12,
        'timesteplength':        3600*24*30 #1 month timesteps
    }
    datasources={
        #
        # Refer to the documentation for information on datasources
        #
        'wcs':[
            'http://turbo.geo.uu.nl/cgi-bin/mapserv?MAP=/data/projectdata/globaldata/globaldata.map'        
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
        'precipitation': {
            'title':        "Precipitation",
            'units':        "mm/month",
            'info':            "Precipitation in mm per month.",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ["#008000","#FFFF00","#FF0000"], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [0.0,500.0],
                'labels':    []
            }
        },
        'temperature': {
            'title':        "Temperature",
            'units':        "deg C",
            'info':            "Surface temperature estimated using the temperature lapse rate.",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ["#008000","#FFFF00","#FF0000"], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [-20,40.0],
                'labels':    []
            }
        },
        'snowmelt': {
            'title':        "Snowmelt",
            'units':        "mm/month",
            'info':            "Snow melt in mm per month.",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ['#3d7afd','#0504aa'], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [1.0,250.0],
                'labels':    []
            }
        },
        'snowfall': {
            'title':        "Snowfall",
            'units':        "mm/month",
            'info':            "Snow fall in mm per month.",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ['#ffffff','#3d7afd'], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [1.0, 1000.0],
                'labels':    []
            }
        },
        'snowpack': {
            'title':        "Snow pack",
            'units':        "mm water equiv/month",
            'info':            "Snow pack in mm water equivalent",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ['#ffffff','#3d7afd'], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [0.01, 1000.0],
                'labels':    []
            }
        },
        'freezing': {
            'title':        "Precipitation Type",
            'units':        "-",
            'info':         "Area where it is freezing or not. In frozen areas all precipiration is assumed to be snow.",
            'datatype':     "Byte",
            'symbolizer':{
                'type':     "categorical", #categorical data must have Byte datatype!!
                'colors':   ['#ffffff','#3d7afd'],
                'values':   [1, 0],
                'labels':   ["Snow","Rain"]
            }
        }
    }
    def initial(self):
        #Fetch the model parameters
        p_lapserate = self.readparam("lapserate") #Default 0.007
        p_tempsmoothing = self.readparam("downscaling_factor") #Default 350m
        p_degreeday = self.readparam("degreeday_melt_factor") #Default 0.01
        
        #Set other required variables
        self.snowPack = 0.0
        self.snowMeltFactor = scalar(p_degreeday)
        self.lapseRate = scalar(p_lapserate)
        self.windowSmooth = scalar(p_tempsmoothing)
        
        #Fetch data from WCS provider
        logger.debug("Loading elevation")
        self.dem =  self.readmap("srtm.elevation")
        
        #Use the elevation model to downscale the coarser temperature maps to
        #the same resolution as the elevation model. This results in a 
        #"tempOffset" map which can be added to the worldclum temperature map
        #to create a high res temperature map.
        logger.debug("Downscaling the temperature maps...")
        temp1 = self.readmap("worldclim.tmean.001")
        temp2 = self.readmap("worldclim.tmean.003")
        temp3 = self.readmap("worldclim.tmean.006")
        temp = temp1 * temp2 * temp3
        test = nominal(temp)
        self.tempZone = clump(test)
        elevZone = areaaverage(self.dem, self.tempZone)
        elevOffs = self.dem - elevZone
        self.tempOffset = (elevOffs*(self.lapseRate*-1))

    def dynamic(self):
        logger.debug("Dynamic! Timestep: %d"%(self.timestep))
        
        #Fetch the temperature and precipitation data for this timestep.
        prec = self.readmap("worldclim.precip.%.3d"%(self.timestep)) #will load a layer like "worldclim.prec.001"
        temp = self.readmap("worldclim.tmean.%.3d"%(self.timestep)) / 10.0 #divide by 10 because worldclim temperature needs to divide by 10 to get degrees
        
        if self.windowSmooth >= 100:
        	temp = windowaverage(self.tempOffset+temp, self.windowSmooth)
        else:
            temp = self.tempOffset + temp
        
        #Determine which precipitation falls as snow, and which as rain, depending on the temperature
        freezing = scalar(temp) < scalar(0.0)
        snowFall = ifthenelse(freezing, prec, 0.0)
        rainFall = ifthenelse(pcrnot(freezing), prec, 0.0)
        self.snowPack = self.snowPack + snowFall
        
        #Calculate which part of the snow pack melts in this timestep
        potentialMelt = ifthenelse(pcrnot(freezing), temp * (1000 * self.snowMeltFactor * 30), 0)
        actualMelt = min(self.snowPack, potentialMelt)
        self.snowPack = self.snowPack - actualMelt
        
        #Report the modelled attributes
        self.report(prec, "precipitation")
        self.report(temp, "temperature")
        self.report(actualMelt, "snowmelt")
        self.report(snowFall, "snowfall")
        self.report(self.snowPack, "snowpack")
        self.report(nominal(freezing),"freezing")
        

    def postdynamic(self):
        logger.debug("Hello postdynamic!")
