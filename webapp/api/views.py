import os
import re
import subprocess
import uuid
import json
import tarfile


from . import api

from flask import g, current_app, render_template, request, jsonify, make_response,Response
from datetime import datetime, timedelta

from ..models import *


@api.route('/')
def home():
    return jsonify(hello="world")

@api.route('/job',methods=["POST","GET"])
def job():
    """
    The job view differs depending on the request method.
    
    A post is interpreted as a request for a model run. Any number of form
    variables can be added to the post, and they will be interpreted as 
    parameter values for the model run if the name matches one of the possible 
    parameters specified in the model code. For example, if the model has a 
    'lapserate' parameter which is a float, you can add a POST variable 
    'lapserate=1.23'. These will always be strings due to the nature of an 
    HTTP post, but an attempt will be made to cast the variable to the same
    type as the one defined in the 'parameters' section of the model code.
    
    An exception can occur while trying to make the job, if that occurs then
    an error code 200 will be returned with a message to let the client know
    something went wrong.
    
    When the job is created successfully it is added to the beanstalk queue
    for further processing on one of the worker machines. Beanstalk jobs are
    strings, so a dict is created and picked which looks like this:
    
        {
            'id':'28f22705-511b-4257-b351-a62636e7d36f',
            'parameters':{
                'lapserate': 0.01,
                'another_parameter':'this one is a string',
            },
            'grid':{
                'bounds':    [177.0,-40.0,178.0,-39.0],
                'cellsize':    100
            },
            'modelcode': '(...the entire model...)'
        }
        
    This dict contains all the information that a worker needs to run and 
    configure the model. It knows the parameters to use, the grid on which
    to run it (i.e. where and what the cell size should be), a unique id
    which is used in communication with the API to let it know when a run
    is completed, to post status updates, or to notify the API that a failure
    occurred.
    
    The modelcode element of the dict contains a string with the actual python
    model code as it has been uploaded or edited in the web application. The
    workers write this code to a temporary file and import it into the 
    PCRaster framework to start up the actual model run.
    
    """
    max_chunks = 1
    model = Model.query.filter_by(name=request.values.get("model_name")).first()
    if model is None:
        raise Exception("Model could not be found.")        
    
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
            job=Job(modelconfig,chunks_to_be_processed,geom)
            db.session.add(job)
            db.session.commit()           
            print "commiting session"
            for jobchunk in job.jobchunks:
                beanstalk.put(jobchunk.pickled)
            return jsonify(job=job.uuid,message="Job accepted"),200
        except Exception as e:
            return jsonify(job='',message="Job not accepted. Hint: %s"%(e)),400
    if request.method=="GET":
        #Todo: make this limit variable on a per model basis...
        #Todo: some kind of check to see if there are clients 
        #      connected to the app to do processing..
        features=[]
        for c in chunks:
            feat = to_shape(c.geom).simplify(0.005)
            
            features.append({
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
        if num_of_chunks_to_be_processed <= 8 and num_of_chunks_to_be_processed >= 1:
            return jsonify(features=features,configkey=modelconfig.key,num_of_chunks_already_processed=num_of_chunks_already_processed,num_of_chunks_to_be_processed=num_of_chunks_to_be_processed,message="Job with configuration %s is acceptable. Job covers %d chunks, of which %d still need to be processed."%(modelconfig.key[0:6],(num_of_chunks_already_processed+num_of_chunks_to_be_processed),num_of_chunks_to_be_processed)),200
        else:
            return jsonify(features=features,configkey=modelconfig.key,num_of_chunks_already_processed=num_of_chunks_already_processed,num_of_chunks_to_be_processed=num_of_chunks_to_be_processed,message="Job with configuration %s cannot be run. The map extent contains %d chunks which can be processed (of %d total) which is too many. Try zooming in a little further."%(modelconfig.key[0:6],num_of_chunks_to_be_processed,(num_of_chunks_already_processed+num_of_chunks_to_be_processed))),400


@api.route('/job/<uuid:job_uuid>',methods=["POST","GET","HEAD"])
def job_status(job_uuid):
    """
    Interact with a job.

    POST: update job status.
    
    POSTing will not happen to a job as a whole but to individual job chunks.    
    
    GET: get the job status
    DELETE: cancel the job
    HEAD: job completed or not completed????maybe no

    Todo: maybe create a job.as_json representation of the job for 
    easy parsing in here. or utilize __dict__ for that and pass the
    whole dict(job) to jsonify.
    """
    job=Job.query.filter_by(uuid=job_uuid.hex).first_or_404()
    jobchunks=job.jobchunks.all()
    jclist=[]
    for jc in jobchunks:
        jclist.append(jc.as_dict)
    #job.update_status()
    if request.method=="GET":
        if request.values.get("verbose","False")=="True":
            return jsonify(
                job=job.uuid,
                message='Found a job!',
                model=job.modelconfiguration.model.name,
                parameters=job.modelconfiguration.parameters,
                jobchunks=jclist,
                status_code=job.status_code,
                status_codes=job.status_codes
            ),200
        else:
            return jsonify(
                job=job.uuid,
                status_code=job.status_code,
                status_message="",
                percent_complete=job.percent_complete,
                results=job.results
            ),200


@api.route('/config/<config_key>',methods=["GET"])
def config_status(config_key):
    """
    Returns a JSON representation of a modelconfiguration instance. This contains
    metadata about the model, reporting information (i.e. output attributes),
    and time information about the model.
    
    The set of parameters which are used for the model run are also included.
    """
    modelconfiguration=ModelConfiguration.query.filter_by(key=config_key).first_or_404()
    return jsonify(modelconfiguration.as_dict)

@api.route('/model/<model_name>',methods=["GET","POST"])
def model_status(model_name):
    """
    REturn or update model code 
    """
    m=Model.query.filter_by(name=model_name).first_or_404()
    if request.method=="GET":
        return Response(m.code,mimetype="text/plain")
    if request.method=="POST":
        try:
            m.updatecode(request.form.get("code"))
            db.session.commit()
            return jsonify(model=m.name,message="Model code updated."),200
        except Exception as e:
            return jsonify(model=m.name,message="Code update failed! Hint: %s"%(e)),400
            
@api.route('/discretization/<discretization_name>/bounds', methods=["GET"])
def discretization_bounds(discretization_name):
    d = Discretization.query.filter_by(name=discretization_name).first_or_404()
    return jsonify(bounds=d.extent_as_bounds)
    
@api.route('/discretization/<discretization_name>/coverage.json', methods=["GET"])
def discretization_coverage(discretization_name):
    d = Discretization.query.filter_by(name=discretization_name).first_or_404()
    return Response(d.coverage_as_geojson,mimetype="application/json")

@api.route('/model/list')
def model_list():
    """
    Returns a list of available models
    """
    pass

@api.route('/model/<model_name>/meta')
def model_meta(model_name):
    """
    Returns metadata about a model. 
    """
    pass

@api.route('/model/<model_name>/code')
def model_code(model_name):
    """
    Returns model code so that a worker can fetch it and run this model.
    """
    m=Model.query.filter_by(name=model_name).first_or_404()
    return Response(m.code,mimetype="text/plain")


@api.route('/pointinfo')
def pointinfo():
    """
    Return information about a point. ideally this should be integrated 
    into the /data/ blueprint like a getfeatureinfo request. Lets see about 
    that...
    """
    pass


@api.route('/job/chunk/<uuid:jobchunk_uuid>/status',methods=["GET"])
def jobchunk_get_status(jobchunk_uuid):
    """
    Interact with a job chunk
    """
    jobchunk=JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first_or_404()
    return jsonify(jobchunk.for_worker),200
    
@api.route('/job/chunk/<uuid:jobchunk_uuid>/status',methods=["POST"])
def jobchunk_post_status(jobchunk_uuid):
    """
    Update a jobchunk's status
    """
    jobchunk=JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first_or_404()
    
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
    
    #Also update the status of the JobChunk's parent Job. As JobChunks are 
    #completed the entire Job also nears completion.
    jobchunk.job.update_status()
    return jsonify(jobchunk=jobchunk.uuid,message='Update acceped.'),200

@api.route('/job/chunk/<uuid:jobchunk_uuid>/log',methods=["GET"])
def jobchunk_get_log(jobchunk_uuid):
    """
    See the log file of this run.
    
    Todo: implement. Use self.status_log field.
    """
    jobchunk=JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first_or_404()
    return Response(jobchunk.status_log, mimetype='text/plain')

@api.route('/job/chunk/<uuid:jobchunk_uuid>/log',methods=["POST"])
def jobchunk_post_log(jobchunk_uuid):
    """
    Post a logfile
    """
    jobchunk = JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first_or_404()

    return jsonify(jobchunk=jobchunk.uuid,message='Update acceped.'),200

@api.route('/job/chunk/<uuid:jobchunk_uuid>/package',methods=["GET"])
def jobchunk_get_package(jobchunk_uuid):
    """
    Download the maps package of this run.
    
    Todo: implement. use flask send_from_directory
    """
    jobchunk=JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first_or_404()
    pass

@api.route('/job/chunk/<uuid:jobchunk_uuid>/package',methods=["POST"])
def jobchunk_post_package(jobchunk_uuid):
    """
    This API endpoint is a deaddrop of sorts for maps. When a chunk has been
    processed with a specific configuration by a worker, the worker will 
    assemble a maps package which is a tar file containing:
        - all the output attributes as optimized tif files
        - many .vrt files for each timestep pointing to the right band of the
          tif file
        - a manifest file in json format specifying what maps are present in 
          the package
        - a runlog which contains the logfile of that particular run, for 
          debugging purposes.
    This tar file is POSTed here with an HTTP post, thereby signaling that the
    model run is complete. Then:
        - the tar file is extracted
        - the map files are stored in the right place
        - the manifest is read and for each entry, a corresponding entry is made
          in the 'map' table.
        - the log file is saved in the database
        - the status on the JobChunk, if everything went ok, is set to complete.
        
    Todo: possibly include a token of sorts which is included when the job is
    sent out and needds to be passed again when posted here for verification.
    """
    f = request.files['package']
    jobchunk=JobChunk.query.filter_by(uuid=jobchunk_uuid.hex).first_or_404()
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
                #           which do not have a corresponding file on disk.
                    #
                    try: maps_list.append(Map(chunk,modelconfiguration,map_dict))
                    except: pass
                db.session.add_all(maps_list)
        tar.close()
        #jobchunk.status_code=1
        #jobchunk.status_message="Processed maps package! Everything is done."
        
        #jobchunk.status_log=request.form.get("log","")
        
        jobchunk.status_percentdone=99        
        
        db.session.commit()
        jobchunk.job.update_status()

    return jsonify(status='ok'),200