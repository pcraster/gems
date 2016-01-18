{% if model_name %}
from gem.model import *

class Model(GemModel):
    """
    Add a description of the {{model_name}} here.
    """
    meta={
        #
        # Metadata
        #
        'name':                 '{{model_name}}',
        'author':               'GEMS',
        'contact':              '',
        'abstract':             'Short abstract of the {{model_name}} model',
        'license':              '',
        'tags':                 ['tag','tag','tag'],
        'discretization':       'world_onedegree_100m',
        'maxchunks':            1
    }
    parameters={
        #
        # These are default params that will be overwritten by params
        # specified in the web application.
        #
        'string_param' :        "a string parameter",
        'int_param':            42,
        'float_param':          0.82,
        'threshold':            0.5
    }
    time={
        'start':                 '2014-01-15T00:00:00',
        'timesteps':             6,
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
        #
        # The reporting section adds metadata to model output attributes.
        # By reporting a map with self.report(<name>) and the name matches
        # keys listed below, that information will be used in the webmap.
        # If you report maps without defining them here it will not show
        # up in the web interface.
        #
        'random': {
            'title':        "A random value",
            'units':        "-",
            'info':            "This is a random value between zero and one.",
            'datatype':        "Float32",
            'symbolizer':{
                'type':        "pseudocolor",
                'clamp':    True,
                'ticks':    5, #ticks only works on pseudocolor symbolizers
                'colors':    ["#008000","#FFFF00","#FF0000"], #["#ff0000","#ffff00","#00ff00","#00ffff","#0000ff","#ff00ff","#ff0000"],
                'values':    [0.0,10.0],
                'labels':    []
            }
        },
        'threshold': {
            'title':        "Threshold",
            'units':        "-",
            'info':         "Area above or below the threshold specified in the model parameter.",
            'datatype':     "Byte",
            'symbolizer':{
                'type':     "categorical", #categorical data must have Byte datatype!!
                'colors':   ['#e50000','#d8dcd6'],
                'values':   [1, 0],
                'labels':   ["Above threshold","Below threshold"]
            }
        },
    }
    def initial(self):
        logger.debug("Hello initial!")
        int_param = self.readparam("int_param")
        logger.debug("The int_param has a value of: %d"%(int_param))

    def dynamic(self):
        logger.debug("Hello dynamic!")
        map_with_random_values = uniform(boolean(1))
        map_with_random_values = map_with_random_values * 10

        logger.debug("Reporting a map at time: %s"%(self.timestamp))
        self.report(map_with_random_values, "random")

        threshold = self.readparam("threshold")
        threshold_map = ifthenelse(map_with_random_values > threshold, nominal(1), nominal(0))
        logger.debug("Using a threshold value of: %.2f"%(threshold))
        self.report(threshold_map, "threshold")

    def postdynamic(self):
        logger.debug("Hello postdynamic!")
{% endif %}