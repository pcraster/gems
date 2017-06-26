

###############################################################################
# Imports
###############################################################################
import os
import uuid
import json
import tarfile

from . import api
from flask import g, current_app, render_template, request, jsonify, make_response, Response, url_for, stream_with_context

import select
from sqlalchemy import text
import datetime


from ..models import *

###############################################################################
# Handle basic authentication for the API. 
# See: http://flask.pocoo.org/snippets/8/
###############################################################################
from functools import wraps
def auth_check(auth):
    if auth is None:
        return False
    user = User.query.filter_by(username=auth.username).first()
    if user is None:
        return False
    return auth.username == user.username and auth.password == user.api_token
    
def requires_auth_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            raise APIException("Access denied. You did not supply any authorization credentials.", status_code=403)
        if not auth or not auth_check(auth):
            raise APIException("Access denied. The token you supplied is not valid.", status_code=403)
        return f(*args, **kwargs)
    return decorated

###############################################################################
# Handle API exceptions with the APIException class. To raise any sort of API
# exception just raise APIException(message, status_code=500). The API will
# return an error JSON document and the accompanying message.
# See: http://flask.pocoo.org/docs/0.10/patterns/apierrors/
###############################################################################
class APIException(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv

@api.errorhandler(APIException)
def handle_api_error(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response
    
###############################################################################
# Here are all the API views. Use the @requires_auth_token decorator to 
# require a token for authenticating to the API.
###############################################################################

@api.route('/', methods=["GET"])
def home():
    """The home view shows a status message which confirms that the system
    is operating normally, and whether the user is authenticated or not. 
    
    **URL Pattern**
    
    ``GET /``
    
    **Parameters**
    
    None.
    
    **Returns**    
    
    200 OK (application/json)
        The system is running normally and you can continue to use it. A JSON
        object is returned::
        
        {
            "authenticated": true, 
            "hello": "world", 
            "message": "Welcome to the GEMS API!", 
            "status": true
        }
        
        In which the authenticated attribute is a boolean value showing 
        whether the authentication of the access token went ok or not. 
        
    503 Service Unavailable (application/json)
        An error occurred in the internal checklist. Something is not ok, it
        could be that there are no workers connected to the system, that
        the work queue has been shut down, the database not available, that
        sort of thing. Check the "message" attribute of the returned JSON
        object for more information
    """
    if beanstalk:
        return jsonify(hello="world",message="Welcome to the GEMS API!", status=True, authenticated=auth_check(request.authorization)),200
    else:
        raise APIException("The work queue is unavailable", status_code=503)
    

@api.route('/job', methods=["GET"])
@requires_auth_token
def job_prognosis():
    """Estimates a prognosis for a job you might want to create later. This 
    can be used as a check to see if your job is acceptable before actually 
    submitting it and checks whether there are chunks in the selected area,
    if they have been run already, and if the extent is not too large for a 
    model run. A prognosis request is also used in the web client to disable or
    enable the "Run Model" button after you pan to another area or change the
    model parameters.

    **URL Pattern**
    
    ``GET /job``

    **Parameters**
    
    This endpoint accepts the same parameters as `webapp.api.views.job_create`_.
    
    model_name (string, required)
        Name of the model you want to run.
        
    bbox (string, required)
        Comma separated bounding box of the model area in lat-lng coordinates.
        For example ``177.0,-40.0,178.0,-39.0``.
        
    *parameter* (optional)
        Any other parameters can be passed to the model. Whether the model uses
        them is up to the model. When a parameter here matches one of the ones
        predefined in the model (for example 'lapserate' in the snowmelt model)
        it will be attempted to convert it to the same type as the default
        parameter (int, float, or string) and passed along in the modelling
        job.
    
    **Returns**    
    
    200 OK (application/json)
        The job prognosis looks acceptable. Feel free to POST the same parameters
        to the `webapp.api.views.job_create`_ endpoint to schedule an actual job.
        The JSON response will look like::
        
            {
                "configkey": "260b90221e570dfe6caa06946a4bd340", 
                "features": [ ... ],
                "message": "Job with configuration 260b90 is acceptable. Job covers 1 chunks, of which 1 still need to be processed.", 
                "num_of_chunks_already_processed": 0, 
                "num_of_chunks_to_be_processed": 1
            }
            
        The list of GeoJSON features (representing the outlines of the chunks
        intersecting the target area) is omitted from the example. A new
        configuration key is also created from the model's parameter set 
        expanded with the parameters passed in the HTTP request.
    
    400 Bad Request (application/json)
        The job does not look acceptable. Probably no chunks were found to run the
        model on, the model was already run in this area with the same
        configuration, or the request contains simply too many chunks. Check the 
        JSON content of the error message for more information.
        
    **To do**
    
    * Includes the matched chunks in geojson format. Used now for creating a 
      red polygon representing the model run area in the interface.
    
    * Refactor so the chunk fetching code at the top is put in a different 
      function. It is the same as in the job_create view.    
    
    """
    model = Model.query.filter_by(name=request.values.get("model_name")).first()

    if model is None:
        raise APIException("Model could not be found.", status_code=404)
    if not model.validated:
        raise APIException("Model is not valid, there is probably something wrong with the code.", status_code=500)
    if model.disabled:
        raise APIException("Model has been deleted.", status=404)

    max_chunks = model.maxchunks    
    modelconfig = model.configure(request.values)    
    
    discretization = Discretization.query.filter_by(name=modelconfig.parameters.get("__discretization__")).first()
    if discretization is None:
        raise APIException("Discretization defined in the model could not be found.", status_code=500)
        
    geom=from_shape(box(*map(float,request.values.get("bbox").split(","))),4326)
    
    jobchunks=JobChunk.query.join(Job).join(Chunk).filter(Job.modelconfiguration_id==modelconfig.id).filter(Chunk.geom.intersects(geom)).filter(JobChunk.status_code==1).with_entities(Chunk.id)
    chunks_already_processed=[c[0] for c in jobchunks]        
    num_of_chunks_already_processed=len(chunks_already_processed)
    
    chunks = None
    if num_of_chunks_already_processed == 0:
        #don't exclude chunks already processed, because using in_() with an
        #empty sequence gives an error that we want to avoid:
        #
        #   /usr/local/lib/python2.7/dist-packages/sqlalchemy/sql/default_comparator.py:35: SAWarning: The IN-predicate on "chunk.id" was invoked with an empty sequence. This results in a contradiction, which nonetheless can be expensive to evaluate.  Consider alternative strategies for improved performance.
        #   return o[0](self, self.expr, op, *(other + o[1:]), **kwargs)
        #print Chunk.geom
        chunks = Chunk.query.filter(Chunk.discretization_id==discretization.id).filter(Chunk.geom.intersects(geom)).order_by(ST_Distance(ST_Centroid(Chunk.geom),ST_Centroid(geom))).limit(max_chunks)
        otherchunks = Chunk.query.filter(Chunk.discretization_id==discretization.id).filter(Chunk.geom.intersects(geom)).order_by(ST_Distance(ST_Centroid(Chunk.geom),ST_Centroid(geom))).offset(max_chunks).limit(100)
    else:
        #if there are some chunks which have already been processed with the
        #same config key then exclude those chunks from the intersect 
        #operation using a negated (~) in_()
        chunks = Chunk.query.filter(Chunk.discretization_id==discretization.id).filter(Chunk.geom.intersects(geom),~Chunk.id.in_(chunks_already_processed)).order_by(ST_Distance(ST_Centroid(Chunk.geom),ST_Centroid(geom))).limit(max_chunks)
        otherchunks = Chunk.query.filter(Chunk.discretization_id==discretization.id).filter(Chunk.geom.intersects(geom),~Chunk.id.in_(chunks_already_processed)).order_by(ST_Distance(ST_Centroid(Chunk.geom),ST_Centroid(geom))).offset(max_chunks).limit(100)
        
    chunks_to_be_processed = [c.id for c in chunks]
    num_of_chunks_to_be_processed = len(chunks_to_be_processed)
    
    #Todo: make this limit variable on a per model basis...
    #Todo: some kind of check to see if there are clients 
    #      connected to the app to do processing..
    features=[[],[]]
    for c in chunks:
        feat = to_shape(c.geom).simplify(0.0005, preserve_topology = False)
        
        features[0].append({
            'type':'Feature',
            'properties':{
                'id':str(c.uuid)
            },
            'geometry':mapping(feat)
        })
        
    for c in otherchunks:
        feat = to_shape(c.geom).simplify(0.0005, preserve_topology = False)
        
        features[1].append({
            'type':'Feature',
            'properties':{
                'id':str(c.uuid)
            },
            'geometry':mapping(feat)
        })

        #print c.geom
    #geom_json = [db.session.scalar(ST_AsGeoJSON(c.geom) for c in chunks)]
    #print geom_json
    if num_of_chunks_to_be_processed == 0:
        return jsonify(features=features,configkey=modelconfig.key,num_of_chunks_already_processed=num_of_chunks_already_processed,num_of_chunks_to_be_processed=num_of_chunks_to_be_processed,message="Job with configuration %s cannot be run. No new chunks were found within the map extent. Change either the model configuration or pan to a different area."%(modelconfig.key[0:6])),400
    if num_of_chunks_to_be_processed >= 1:
        return jsonify(features=features,configkey=modelconfig.key,num_of_chunks_already_processed=num_of_chunks_already_processed,num_of_chunks_to_be_processed=num_of_chunks_to_be_processed,message="Job with configuration %s is acceptable. Job covers %d chunks, of which %d still need to be processed."%(modelconfig.key[0:6],(num_of_chunks_already_processed+num_of_chunks_to_be_processed),num_of_chunks_to_be_processed)),200
        
    #if num_of_chunks_to_be_processed <= 8 and num_of_chunks_to_be_processed >= 1:
    #    return jsonify(features=features,configkey=modelconfig.key,num_of_chunks_already_processed=num_of_chunks_already_processed,num_of_chunks_to_be_processed=num_of_chunks_to_be_processed,message="Job with configuration %s is acceptable. Job covers %d chunks, of which %d still need to be processed."%(modelconfig.key[0:6],(num_of_chunks_already_processed+num_of_chunks_to_be_processed),num_of_chunks_to_be_processed)),200
    #else:
    #    return jsonify(features=features,configkey=modelconfig.key,num_of_chunks_already_processed=num_of_chunks_already_processed,num_of_chunks_to_be_processed=num_of_chunks_to_be_processed,message="Job with configuration %s cannot be run. The map extent contains %d chunks which can be processed (of %d total) which is too many. Try zooming in a little further."%(modelconfig.key[0:6],num_of_chunks_to_be_processed,(num_of_chunks_already_processed+num_of_chunks_to_be_processed))),400
    
@api.route('/job', methods=["POST"])
@requires_auth_token
def job_create():
    """Creates a new simulation job for a given model and parameter set.
    
    Any number of form
    variables can be added to the post, and they will be interpreted as 
    parameter values for the model run if the name matches one of the possible 
    parameters specified in the model code. For example, if the model has a 
    'lapserate' parameter which is a float, you can add a POST variable 
    'lapserate=1.23'. These will always be strings due to the nature of an 
    HTTP post, but an attempt will be made to cast the variable to the same
    type as the one defined in the 'parameters' section of the model code.

    **URL Pattern**
    
    ``POST /job``

    **Parameters**
    
    This endpoint accepts the same parameters as `webapp.api.views.job_prognosis`_.
    
    model_name (string, required)
        Name of the model you want to run.
        
    bbox (string, required)
        Comma separated bounding box of the model area in lat-lng coordinates.
        For example ``177.0,-40.0,178.0,-39.0``.
        
    *parameter* (optional)
        Any other parameters can be passed to the model. Whether the model uses
        them is up to the model. When a parameter here matches one of the ones
        predefined in the model (for example 'lapserate' in the snowmelt model)
        it will be attempted to convert it to the same type as the default
        parameter (int, float, or string) and passed along in the modelling
        job.

    **Returns**
    
    202 Accepted (application/json)
        The job has been accepted for processing. The following response 
        content will be returned with your job id substituted::
        
            {
                "job": "c2fb283c-559c-41d2-8772-691233619499", 
                "message": "Job accepted. You can check the completion status of this job at: http://127.0.0.1:5000/api/v1/job/c2fb283c-559c-41d2-8772-691233619499"
            }

    503 Service Unavailable (application/json)
        The service is not available. No beanstalk connection found or there are
        no workers watching the work queue.
        
    500 Internal Server Error (application/json)
        Some other exception occurred. See the JSON response content for more
        information.

    """
    model = Model.query.filter_by(name=request.values.get("model_name")).first()
    
    if model is None:
        raise APIException("Model could not be found.", status_code=404)
        
    if not model.validated:
        raise APIException("Model is not valid, there is probably something wrong with the code.", status_code=500)
        
    if model.disabled:
        raise APIException("Model has been deleted.", status=404)
        
    if not beanstalk.connected:
        raise APIException("GEMS API cannot connect to the work queue")
        
    if not beanstalk.workers_watching:
        raise APIException("There are no workers watching the work queue. Models cannot be processed without workers.")
    
    max_chunks = model.maxchunks    
    user = User.query.filter_by(username=request.authorization.username).first()    
    modelconfig = model.configure(request.values)    
    
    discretization = Discretization.query.filter_by(name=modelconfig.parameters.get("__discretization__")).first()
    if discretization is None:
        raise Exception("Discretization could not be found.")
        
    geom=from_shape(box(*map(float,request.values.get("bbox").split(","))),4326)
    
    jobchunks=JobChunk.query.join(Job).join(Chunk).filter(Job.modelconfiguration_id==modelconfig.id).filter(Chunk.geom.intersects(geom)).filter(JobChunk.status_code==1).with_entities(Chunk.id)
    chunks_already_processed=[c[0] for c in jobchunks]        
    num_of_chunks_already_processed=len(chunks_already_processed)
    
    chunks = None
    if num_of_chunks_already_processed == 0:
        #don't exclude chunks already processed, because using in_() with an
        #empty sequence gives an error that we want to avoid:
        #
        #   /usr/local/lib/python2.7/dist-packages/sqlalchemy/sql/default_comparator.py:35: SAWarning: The IN-predicate on "chunk.id" was invoked with an empty sequence. This results in a contradiction, which nonetheless can be expensive to evaluate.  Consider alternative strategies for improved performance.
        #   return o[0](self, self.expr, op, *(other + o[1:]), **kwargs)
        #print Chunk.geom
        chunks = Chunk.query.filter(Chunk.discretization_id==discretization.id).filter(Chunk.geom.intersects(geom)).order_by(ST_Distance(ST_Centroid(Chunk.geom),ST_Centroid(geom))).limit(max_chunks)
    else:
        #if there are some chunks which have already been processed with the
        #same config key then exclude those chunks from the intersect 
        #operation using a negated (~) in_()
        chunks = Chunk.query.filter(Chunk.discretization_id==discretization.id).filter(Chunk.geom.intersects(geom),~Chunk.id.in_(chunks_already_processed)).order_by(ST_Distance(ST_Centroid(Chunk.geom),ST_Centroid(geom))).limit(max_chunks)
        
    chunks_to_be_processed = [c.id for c in chunks]
    num_of_chunks_to_be_processed = len(chunks_to_be_processed)
        
    if request.method=="POST":
        try:
            job=Job(modelconfig,chunks_to_be_processed,geom,user)
            db.session.add(job)
            db.session.commit()     
            for jobchunk in job.jobchunks:
                beanstalk.queue.put(jobchunk.pickled)
                
        except BeanstalkWorkersFailure as e:
            return jsonify(job='', message="Job not accepted. %s"%(e)),503
        except BeanstalkConnectionFailure as e:
            return jsonify(job='', message="Job not accepted. %s"%(e)),503
        except Exception as e:
            return jsonify(job='', message="Job not accepted. %s"%(e)),500
        else:
            status_url = url_for("api.job_status", job_uuid=str(job.uuid), _external=True)
            return jsonify(job=job.uuid, message="Job accepted. You can check the completion status of this job at: %s"%(status_url)),202
            

@api.route('/job/<uuid:job_uuid>', methods=["GET"])
@requires_auth_token
def job_status(job_uuid):
    """Returns a JSON object of a job which describes the current job status.

    **URL Pattern**
    
    ``GET /job/<uuid:job_uuid>``

    **Parameters**
    
    None.
    
    **Returns**
    
    200 OK (application/json)
        The job was found and has been completed. A JSON object is returned::
        
            {
                "job": "f7ed869d-b52e-4dd2-b72b-d71f9fb65014", 
                "percent_complete": 100, 
                "results": {
                    "attributes": [], 
                    "config_key": "260b90221e570dfe6caa06946a4bd340", 
                    "timesteps": [ ... ]
                }, 
                "status_code": 1, 
                "status_message": ""
            }
        
        The results element contains the modelling results (attributes and 
        timesteps for a particular configuration.) The results element is empty 
        when the model is not yet finished processing.
        
    202 Accepted (application/json)
        The job has been accepted and is being processed, but is not yet
        completed. A JSON object is returned::
        
            {
                "job": "f7ed869d-b52e-4dd2-b72b-d71f9fb65014", 
                "percent_complete": 0, 
                "results": [], 
                "status_code": 0, 
                "status_message": ""
            }
        
    404 Not Found (application/json)
        No job with this id exists.
    
    """
    job = Job.query.filter_by(uuid=job_uuid.hex).first()
    
    if job is None:
        raise APIException("The job could not be found.", status_code=404)

#    jobchunks = job.jobchunks.all()
#    jclist=[]
#    for jc in jobchunks:
#        jclist.append(jc.as_dict)
        
    http_status = 200 if job.percent_complete != 100 else 202
    return jsonify(
        job = job.uuid,
        status_code = job.status_code,
        status_message = "",
        percent_complete = job.percent_complete,
        results = job.results
    ),http_status
    

@api.route('/job/<uuid:job_uuid>/log', methods=["GET"])
def job_log(job_uuid):
    """Returns a plaintext logfile of the specified model run.

    **URL Pattern**
    
    ``GET /job/<uuid:job_uuid>/log``

    **Parameters**
    
    None.
    
    **Returns**
    
    200 OK (text/plain)
        The specified job was found and a logfile is returned in text/plain
        format.
        
    404 Not Found (application/json)
        No job with this id exists.
    
    """
    job = Job.query.filter_by(uuid=job_uuid.hex).first()
    if job is None:
        raise APIException("The job could not be found.", status_code=404)
    else:
        return Response(job.as_text ,mimetype="text/plain")
#    jobchunks = job.jobchunks.all()
#    jclist=[]
#    for jc in jobchunks:
#        jclist.append(jc.as_dict)
#        
#    http_status = 200 if job.percent_complete != 100 else 202
#    return jsonify(
#        job = job.uuid,
#        status_code = job.status_code,
#        status_message = "",
#        percent_complete = job.percent_complete,
#        results = job.results
#    ),http_status

@api.route('/config/<config_key>',methods=["GET"])
def config_status(config_key):
    """Returns a JSON representation of a modelconfiguration instance. This 
    contains metadata about the model, reporting information (i.e. output 
    attributes), and time information about the model. The set of parameters 
    which are used for the model run are also included.
    
    **URL Pattern**
    
    ``GET /config/<config_key>``

    **Parameters**
    
    None.
    
    **Returns**
    
    200 OK (application/json)
        Returns a JSON document of the model configuration.
        
    404 Not Found (application/json)
        This configuration key does not exist.
        
    """
    config = ModelConfiguration.query.filter_by(key=config_key).first()
    if config is None:
        raise APIException("The model configuration could not be retrieved with the specified config key.", status_code=404)
    else:
        return jsonify(config.as_dict),200
        
@api.route('/shortcon/<config_key>',methods=["GET"])
def shortcon_status(config_key):
    """Returns a JSON representation of a modelconfiguration instance. This 
    contains metadata about the model, reporting information (i.e. output 
    attributes), and time information about the model. The set of parameters 
    which are used for the model run are also included.
    
    **URL Pattern**
    
    ``GET /config/<config_key>``

    **Parameters**
    
    None.
    
    **Returns**
    
    200 OK (application/json)
        Returns a JSON document of the model configuration.
        
    404 Not Found (application/json)
        This configuration key does not exist.
        
    """
    config = ModelConfiguration.query.filter_by(key=config_key).first()
    if config is None:
        raise APIException("The model configuration could not be retrieved with the specified config key.", status_code=404)
    else:
        return jsonify(config.as_short_dict),200
        
@api.route('/model/<model_name>',methods=["GET"])
def model_code_view(model_name):
    """
    View model code.
    """
    m = Model.query.filter_by(name=model_name).first_or_404()
    return Response(m.code, mimetype="text/plain")

@api.route('/model/<model_name>',methods=["POST"])
@requires_auth_token
def model_status(model_name):
    """
    Update model code
    
    Todo:
    * If a model does not exist yet, try to create it.
    * When creating a model, call updatecode() with the contents of the file that was POSTed.
    """
    m = Model.query.filter_by(name=model_name).first()
    user = User.query.filter_by(username=request.authorization.username).first()
    if not user.is_admin:
        raise APIException("Code update failed! Your token was ok, but only admin users can update code. Sorry!", status_code=401)
        
    try:
        m.updatecode(request.form.get("code"))
        return jsonify(model=m.name,message="Code for model %s updated! Current revision: %d"%(m.name, m.version)),200
    except Exception as e:
        raise APIException("Code update failed! Hint: %s"%(e), status_code=400)
        #return jsonify(model=m.name,message="Code update failed! Hint: %s"%(e)),400
            
@api.route('/discretization/<discretization_name>/bounds', methods=["GET"])
def discretization_bounds(discretization_name):
    """Returns a bounding box of the discretization
    
    """
    d = Discretization.query.filter_by(name=discretization_name).first_or_404()
    return jsonify(bounds=d.extent_as_bounds)
    
@api.route('/discretization/<discretization_name>/coverage.json', methods=["GET"])
def discretization_coverage(discretization_name):
    """Returns a geojson coverage of the discretization
    
    """
    d = Discretization.query.filter_by(name=discretization_name).first_or_404()
    return Response(d.coverage_as_geojson,mimetype="application/json")

@api.route('/job/chunk/<uuid:jobchunk_uuid>', methods=["GET","POST"])
def jobchunk_status(jobchunk_uuid):
    """Returns (in case of a GET request) or updates (in case of a POST 
    request) the status of a particular Job chunk. This functionality is used
    mostly by the backend, as the processing script working on the model will
    send intermittent POST requests to this API endpoint, telling it how far
    along the model run of this chunk is.
    
    When the processing of the chunk is completed and the model is unloaded, 
    another POST request will be made to this endpoint to upload the logfile 
    of the model run. This is stored in the database so that it can be viewed
    in the web app.
    
    **URL Pattern**
    
    ``GET /job/chunk/<uuid:jobchunk_uuid>``
    
    ``POST /job/chunk/<uuid:jobchunk_uuid>``

    **Parameters**
    
    status_code (int, optional)
        A status code to signify the status of this JobChunk. Negative values
        are errors, 1 is complete, and 0 is still processing.
        
    status_message (string, optional)
        A message accompanying the status update. Only one status message is
        stored, so it is overwritten every time a new one is posted.
        
    status_percentdone (int, optional)
        An approximation of how much percent complete this Job Chunk is.
        
    log (string, optional)
        Contents of the logfile.
    
    **Returns**
    
    200 OK (application/json)
        The request was fulfilled successfully. In a GET request a summary of
        the jobchunk it returned (a jsonified``as_dict`` property) and in case
        of a POST request it means the update succeeded.
        
    404 Not Found (application/json)
        No jobchunk with the specified id could be found.
        
    500 Internal Server Error (application/json)
        An error occurred while trying to update the resource. Check the JSON
        response for more information.
    
    
    """
    jobchunk = JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first()
    
    if jobchunk is None:
        raise APIException("JobChunk could not be found.", status_code=404)
    
    if request.method == "GET":
        return jsonify(jobchunk.as_dict), 200
    
    if request.method == "POST":
        try:
            status_code=request.form.get("status_code",None)
            if status_code != None:
                jobchunk.status_code=status_code
                
            status_message=request.form.get("status_message",None)
            if status_message != None:
                jobchunk.status_message=status_message
                
            status_percentdone=request.form.get("status_percentdone",None)
            if status_percentdone != None:
                jobchunk.status_percentdone=status_percentdone
                
            status_log = request.form.get("log", None)
            if status_log != None:
                jobchunk.status_log = status_log    
                
            db.session.commit()
            
            #Also call the update_status method of the JobChunk's parent Job,
            #that way the parent Job will also be aware of how far along the
            #job in its entiriy is.
            jobchunk.job.update_status()
        except Exception as e:
            raise APIException("JobChunk could not be updated.", status_code=500, exception=e)
        else:
            return jsonify(jobchunk=jobchunk.uuid, message='Update acceped.'),200

@api.route('/job/chunk/<uuid:jobchunk_uuid>/log',methods=["GET"])
def jobchunk_log(jobchunk_uuid):
    """Returns a plaintext log file of the model run of this job chunk.
    
    **URL Pattern**
    
    ``GET /job/chunk/<uuid:jobchunk_uuid>/log``

    **Parameters**
    
    None.
    
    **Returns**
    
    200 OK (text/plain)
        The request was fulfilled successfully. In a GET request a summary of
        the jobchunk it returned (a jsonified``as_dict`` property) and in case
        of a POST request it means the update succeeded.
        
    404 Not Found (application/json)
        No jobchunk with the specified id could be found.

    """
    jobchunk = JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first()

    if jobchunk is None:
        raise APIException("JobChunk could not be found.", status_code=404)
    else:
        return Response(jobchunk.status_log, mimetype='text/plain')

@api.route('/job/chunk/<uuid:jobchunk_uuid>/maps', methods=["GET","POST"])
def jobchunk_maps(jobchunk_uuid):
    """
    This API endpoint is a deaddrop of sorts for maps. When a chunk has been
    processed with a specific configuration by a worker, the worker will 
    assemble a maps package, which is essentially a tar file containing:
    
        * One optimized tif file for each output attribute
        * Many .vrt files for each timestep pointing to the right band of the
          original tif file.
        * a manifest file in json format specifying what maps are present in 
          the package. This manifest will be imported in the Map table.
        * a runlog which contains the logfile of that particular run, for 
          debugging purposes.
          
    This tar file is submitted to this endpoint with HTTP POST request, 
    thereby also signaling that the model run is complete. Then:
    
        * The tar file is extracted.
        * The map files are stored in the right place on disk.
        * The manifest is read and for each entry, a corresponding entry is 
          made in the Map table.
        
    A GET request to this endpoint will let the user download the maps package
    as it was submitted by the processing script. This is mainly for debugging
    purposes but could prove useful later on as well. For example if you want
    to view the original model outputs of a chunk before they have been 
    reprojected or reassembled into a web map.

    **URL Pattern**
    
    ``POST /job/chunk/<uuid:jobchunk_uuid>/maps``
    
    ``GET /job/chunk/<uuid:jobchunk_uuid>/maps``

    **Parameters**
    
    package (file, required when using POST)
        Contains the tar-ed maps package.
    
    **Returns**
    
    200 OK (download)
        When downloading the maps package status 200 is returned.
    
    201 Created (application/json)
        The maps package was processed successfully, and the new resources
        (all the maps) were created successfully in the database.
        
    404 Not Found (application/json)
        No jobchunk with the specified id could be found.
        
    **To do**

    * Implement the GET method functionality
    * Add authentication, admin access only.
    * Add some more error checking and better exception handling here, for example
      when no file is added, file is corrupt, missing data, or if it can't be 
      saved locally, or when the maps can't be created in the database.
    
    """
    jobchunk = JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first()

    if jobchunk is None:
        raise APIException("JobChunk could not be found.", status_code=404)    
    
    if request.method == "GET":
        raise APIException("Downloading maps packages is not implemented yet.", status_code=501)    
        
    if request.method == "POST":
        f = request.files['package']
        
        jobchunk_uuid=str(jobchunk.uuid)
        modelconfiguration=jobchunk.job.modelconfiguration
        chunk=jobchunk.chunk
        
        incoming_maps_dir=os.path.join(current_app.config["HOME"],"incoming_maps")
        if not os.path.isdir(incoming_maps_dir):
            os.makedirs(incoming_maps_dir)
    
        maps_dir=os.path.join(current_app.config["HOME"],"maps")           
        if not os.path.isdir(maps_dir):
            os.makedirs(maps_dir)
        
        maps_package=os.path.join(incoming_maps_dir,"results-jobchunk-%s.tar"%(jobchunk_uuid))
        f.save(maps_package)
        
        if tarfile.is_tarfile(maps_package):
            print "Maps package %s can be read!"%(maps_package)
            tar = tarfile.open(maps_package)
            for member in tar.getmembers():
                if member.name!="manifest.json":
                    tar.extract(member,path=maps_dir)
                else:
                    manifest=tar.extractfile(member)
                    maps_list=[]
                    maps_json=json.loads(manifest.read())
                    for map_dict in maps_json:
                        #
                        #Todo: check that the file actually exists and that a manifest is 
                        #      present, otherwise we may be adding maps to the mapindex
                        #      which do not have a corresponding file on disk.
                        #
                        try: maps_list.append(Map(chunk,modelconfiguration,map_dict))
                        except: pass
                    db.session.add_all(maps_list)
            tar.close()
            jobchunk.status_percentdone=99        
            db.session.commit()
            jobchunk.job.update_status()
        else:
            raise APIException("The file submitted as a maps package could not be recognised as a tar file", status_code=400)   
    
        return jsonify(status='ok', message='Maps package processed successfully.'), 201

@api.route('/worker/ping', methods=["POST"])
@requires_auth_token
def worker_ping():
    """
    Endpoint for worker pings to let the API know whether a worker is still
    actively watching the queue.
    
    **URL Pattern**
    
    ``POST /worker/ping``

    **Parameters**
    
    worker_uuid
        The self-generated UUID of the worker. If a worker is new and reports
        its first ping, a new Worker instance will be created with the uuid
        provided.
    
    **Returns**
    
    200 OK (download)
        The ping was registered correctly.
    
    400 Bad Request (application/json)
        No ``worker_id`` parameter was provided.
        
    403 Forbidden (application/json)
        You must provide an admin token to register pings. Not implemented at
        this time.
        
    **To do**

    * Allow only admin token to send pings.
    * Update the model to also allow pings to send other data. Add a JSON field
      ``properties`` to the model and update this with any other allowed 
      POST parameters. This would allow workers to also send some statistics,
      status, or when they are killed allow them to let the API know that the
      worker is no longer functional.
    
    """
    worker_uuid = request.form.get("worker_uuid", None)
    if worker_uuid is None:
        APIException("No worker uuid provided.", status_code=400)
    else:
        worker = Worker.query.filter_by(uuid=worker_uuid).first()
        if worker is None:
            worker = Worker(worker_uuid)
            db.session.add(worker)
        worker.ping()
        db.session.commit()
    return jsonify(status='ok', message='Thank you %s, come again!'%(worker.name)), 200
    
@api.route('/notifications')
def notifications():
    def yield_notifications():
        yield "retry: 3600000\n\n"
        conn = db.engine.connect()
        conn.execute(text("LISTEN gemsnotifications;").execution_options(autocommit=True))
        #while 1:
            #if select.select([conn.connection],[],[],5) == ([],[],[]):
            #    #print "Timeout"
            #    #continue
            #    print "timeout!"
            #else:
        while 1:
            conn.connection.poll()
            while conn.connection.notifies:
                notify = conn.connection.notifies.pop()
                print "Got NOTIFY:", datetime.datetime.now(), notify.pid, notify.channel, notify.payload
                yield "data:%s\n\n"%(notify.payload)
            print "lalal"
                
    if request.headers.get('accept') == 'text/event-stream':
        return Response(stream_with_context(yield_notifications()), content_type='text/event-stream')
    else:
        return Response(stream_with_context(yield_notifications()), content_type='text/plain')

@api.route('/<path:path>')
def api_catch_all(path):
    raise APIException("The API endpoint you are trying to access was not found. Please check the GEMS API documentation for valid API endpoints.", status_code=404)