from gem.model import *

class Model(GemModel):
    """
    Add a description of the life here.
    """
    meta={
        #
        # Metadata
        #
        'name':                 'life',
        'author':               'Mr. Conway',
        'contact':              '',
        'abstract':             'Conway\'s Game of Life',
        'license':              '',
        'tags':                 ['cellular automata','life','conway'],
        'discretization':       'world_onedegree_100m',
        'maxchunks':            1
    }
    parameters={
        #
        # These are default params that will be overwritten by params
        # specified in the web application.
        #
        'threshold':            0.2
    }
    time={
        'start':                 '2014-01-15T00:00:00',
        'timesteps':             24,
        'timesteplength':        3600*24 #1 day timesteps
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
        'alive': {
            'title':        "Alive cells",
            'units':        "-",
            'info':         "Cells which are alive.",
            'datatype':     "Byte",
            'symbolizer':{
                'type':     "categorical", #categorical data must have Byte datatype!!
                'colors':   ['#000000'],
                'values':   [1],
                'labels':   ["Alive"]
            }
        },
        'aliveneighbours': {
            'title':        "Alive neighbours",
            'units':        "-",
            'info':            "Number of alive neighbours",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    4, #ticks only works on pseudocolor symbolizers
                'colors':    ["#008000","#FFFF00","#FF0000"], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [0.5,8.5],
                'labels':    []
            }
        },
    }
    def initial(self):
    	setglobaloption("unitcell")
        initial_alive_threshold = self.readparam("threshold")
        logger.debug("Setting cells above %.2f to be alive!"%(initial_alive_threshold))
        random_values = uniform(1)
        self.alive = random_values < initial_alive_threshold

    def dynamic(self):
        alive_scalar = scalar(self.alive)
        num_of_alive_neighbours = windowtotal(alive_scalar,3) - alive_scalar
        
        self.report(scalar(num_of_alive_neighbours),"aliveneighbours")
    	alive_nominal = nominal(self.alive)
        self.report(alive_nominal, "alive")
        
        three_alive_neighbours = num_of_alive_neighbours == 3
        birth = pcrand(three_alive_neighbours, pcrnot(self.alive))
        
        survival_a = pcrand((num_of_alive_neighbours == 2), self.alive)
        survival_b = pcrand((num_of_alive_neighbours == 3), self.alive)
        
        survival = pcror(survival_a, survival_b)
        self.alive = pcror(birth, survival)
        
    def postdynamic(self):
        logger.debug("Hello postdynamic!")


