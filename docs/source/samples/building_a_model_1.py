# samples/building_a_model_1.py

from gem.model import *

class my_environmental_model(GemModel):
    """
        The python docstring can be used for additional documentation or 
        description of the model. Currently the docstring is not used anywhere.        
    """
    
    #
    # The meta, parameters, time, datasources, and reporting class attributes
    # are used by GEMS to manage the model execution.
    #
    meta={
        # See: Model Metadata section
    }
    parameters={
        # See: Model Parameters sectuin
    }
    time={
        # Time definition
    }
    datasources={
        # Set up datasources
    }
    reporting={
        # Set up reporting
    }
    
    #
    # Below are the PCRaster Python methods that control the model flow.
    #
    def initial(self):
        # Model's initial section
        logger.debug("Hello initial!")

    def dynamic(self):
        # Model's dynamic section (called for each timestep)
        logger.debug("Hello dynamic!")
        
    def postdynamic(self):
        # Model's postdynamic section 
        logger.debug("Hello postdynamic!")