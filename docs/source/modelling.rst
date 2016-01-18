Building Models
===============

This chapter contains information on how to build environmental models in the GEMS framework. Currently only administrator users can build or edit models.

.. contents::
   :depth: 2
   :local:

Differences with PCRaster
-------------------------
Before starting, there are several differences between traditional PCRaster models and those running in the GEMS environment that you should be aware of. The most important ones are:

* GEMS extends the PCRaster-Python framework with additional functionality that is needed (or convenient) for running models in a web environment. A GEMS model is an instance of the ``GemModel`` class defined in ``~/processing/gem/model.py``. The ``GemModel`` extends PCRaster-Python's ``DynamicModel`` and a custom ``ModelReporter`` as base classes with some new functionality. ``ModelReporter`` is part of GEMS and takes care of reporting output maps.

* You don't need to worry about clone maps. GEMS automatically creates a clone map based on cell size and the Chunk that it is going to do a model run on.

* There are no PCRaster .map files. Input data is read with GDAL, and output data is saved in memory as numpy arrays at the time of reporting. At the end of the model run these reported layers are dumped to a GeoTiff file (one for each output attribute) and optimizations (compression, overviews) are applied. See `Reporting`_

* GEMS models are configured using Python class attributes ``meta``, ``time``, ``parameters``, ``reporting``, and ``datasources``. See `Configuration`_.

* GEMS models include some additional metadata about the model. See `Metadata`_.

* GEMS models use real UTC time. Each model must have a UTC start time and a timestep length. The UTC time for subsequent timesteps is calculated from the start time by adding the number of seconds multiplied by the current timestep. Any maps reported before or after the dynamic section of the model are assigned the time of the first and last timestep, respectively. The ``timestamp`` property of a ``GemsModel`` instance returns a datetime object representing the current model time. See `Time`_

* GEMS separates model parameters from model code. The parameters are defined in the ``parameters`` class attribute, and can be overwritten when POSTing a processing job to the API. The ``GemModel`` class provides a ``readparam`` method which can be used to read parameter values. See `Parameters`_.

* GEMS uses data providers to provide the model with input maps. Input data cannot be read from PCRaster map files as usual, but must be requested from a data provider. This data provider will then obtain the data somehow (for example by requesting it from a WCS server or reading it from a database) and return a PCRaster field object that can be used in the model. See `Data Providers`_.

Creating a new model
--------------------
New models can be created in the admin interface. Log in as an administrator, and in the bottom right will be a box "Create a new model". Enter a name using only alphanumeric characters or underscores, and hit "Create". This will create an empty (and invalid) model.

To set up a bare-bones model copy the following code:

.. literalinclude:: samples/building_a_model_1.py

A logger made available to the model, allowing you to add debugging code to your model run. The log output of a particular model run can be viewed using the API.

Configuration
-------------
GEMS uses Python class attributes to define the model configuration. `Refer to this link <http://www.toptal.com/python/python-class-attributes-an-overly-thorough-guide>`_ for more information about class attributes. The ``meta``, ``time``, ``parameters``, and ``reporting`` attributes are stored in the database as PostgreSQL JSON fields. See `GEMS Data Model`_ for more information.

Metadata
--------
The model metadata section is used to define additional properties to the model, such as the model name, author, contact information, and a short abstract. The following properties are required:

==============  ===================================================================
Name            Description
==============  ===================================================================
name            The model name (do not change this afterwards)
discretization  (default: world_onedegree_100m) The name of the discretization/chunkscheme that this model should run on
maxchunks       (default: 1) The maximum number of chunks that are allowed in a job.
==============  ===================================================================

The maximum number of chunks depends largely on how computationally heavy the model is, and how many 
workers there are available to do the processing. A sample metadata section looks like::

    meta={
        #
        # Metadata
        #
        'name':                 'pcrtopo',
        'author':               'Koko Alberti',
        'contact':              'kokoalberti@fastmail.nl',
        'abstract':             'Calculates topographic derivates from the SRTM digital elevation model.',
        'license':              'All Rights Reserved',
        'tags':                 ['topography','SRTM','slope','aspect'],
        'discretization':       'world_onedegree_100m',
        'maxchunks':            2
    }

The model editor or the API will produce an error when you try to use a discretization which does not exist.

Parameters
----------

GEMS separates the model parameters from the model code. The model's default parameters can be defined in the parameters section::

    parameters={
        #
        # These are default params that will be overwritten by params
        # specified in the web application. Use only alphanumeric and
        # space characters for parameter names!!!
        #
        'parameter1':            12.323,
        'lapserate':             0.2,
        'anewparameter':         0.55,
        'max_distance':          180, 
        'scenario':              'A',
        'some_other_param':      2.3
    }

In the model, you can read the parameters using the ``readparam`` method of a ``GemModel`` instance. For example, the following ``initial`` section::

    def initial(self):
    	#Fetch parameters
        lapserate = self.readparam("lapserate") #this will be a float
        scenario = self.readparam("scenario")   #this will be a string
        
        #Print some debug info
        logger.debug("The lapse rate for this run is: %.2f"%(lapse_rate))
        
        #Turn it into a spatial field using PCRaster scalar() function
        self.lapserate=scalar(lapserate)

        #Decisions, decisions...
        if scenario == "A":
            logger.debug("Do the one thing")
        else:
            logger.debug("Do the other thing")

Will get the value of the ``lapserate`` parameter from the configuration block. The ``readparam`` function returns a Python variable, not a PCRaster map. Therefore, if you want to use the value as a spatially explicit value (essentially a field) you need to use PCRaster's scalar() or nominal() or boolean() to convert it.

The **type** of the variable is always inferred from the Python type. For example::

    parameters={
        'anewparameter':         0.55,  #This is a float
        'max_distance':          180,   #This is an int
        'scenario':              'A',   #This is a string
    }

The values defined in the ``parameters`` section can be considered defaults, and can be overwritten by the user when they request a model run. When a model run is requested through the API or the web interface, all the POST parameters are matched to the model parameters. If there is a match, we try to convert the string value from the POST request to the type of Python variable defined in the parameters section. So the following POST request::

    POST /api/v1/job	bbox=<bounding box of the request>
                        model_name=my_environmental_model
                        max_distance=120
                        scenario=A
                        test=123

In this case GEMS will recognise ``max_distance`` and ``scenario`` as valid parameters, and try to convert the strings received in the POST request (all HTTP POST variable are per definition strings) to an int and a string respectively. Because no variable ``test`` is defined in the ``parameters`` section it is discarded. The ``bbox`` and the ``model_name`` parameters are reserved for defining which model you want to run, and what area you want to run it on.

Time
----

Reporting
---------

Data Providers
--------------

WCS Provider
^^^^^^^^^^^^

GFS Provider
^^^^^^^^^^^^

OSM Provider
^^^^^^^^^^^^

Creating your own provider
^^^^^^^^^^^^^^^^^^^^^^^^^^

Putting It All Together
-----------------------


Example Models
--------------

GEMS comes with various example models.

Todo for each model: description, table with input params, output maps.

life
^^^^

waterworld
^^^^^^^^^^

globerosion
^^^^^^^^^^^

pcrtopo
^^^^^^^

pcrsnow
^^^^^^^

example
^^^^^^^

cosmo
^^^^^

forecast
^^^^^^^^

