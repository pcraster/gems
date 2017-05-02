#!/usr/bin/env python

"""
GEMS Processing Client
"""

import os
import sys
import time
import argparse
import requests
import beanstalkc
import json
import multiprocessing
import uuid
import cPickle
import logging
import signal 


from osgeo import gdal, ogr, osr, gdalconst
from StringIO import StringIO
from gem.model import GemModel
from gem.framework import GemFramework

class JobParseFailure(Exception): pass
class JobProcessingFailure(Exception): pass
class JobReportingFailure(Exception): pass

def worker(worker_uuid, args, gems_api, gems_beanstalk, gems_auth, gems_tube):
    #
    # Set up logging
    #
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    
    #
    # Add a filehandler which writes to the log file
    #
    filehandler = logging.FileHandler('/tmp/worker-%s.log'%(worker_uuid))  
    filehandler.setLevel(logging.ERROR)   
    filehandler.setFormatter(formatter)    
    logger.addHandler(filehandler)
    
    #
    # Add a streamhandler for writing log output to stdout
    #
    stdouthandler = logging.StreamHandler(sys.stdout)
    stdouthandler.setLevel(logging.INFO)
    stdouthandler.setFormatter(formatter)
    logger.addHandler(stdouthandler)

    worker_name = worker_uuid[0:6]

    try:
        beanstalk = beanstalkc.Connection(host=gems_beanstalk, port=11300)
        beanstalk.watch(gems_tube)
        logger.info("[Worker %s] Connected to beanstalk message queue on tube '%s'."%(worker_name,beanstalk.using()))
    except Exception as e:
        logger.critical("[Worker %s] Could not connect to beanstalk work queue."%(worker_name))
        sys.exit(1)

    try:
        while True:
            # Add a streamhandler for writing log output to a StringIO which is
            # flushed after each model run to spit out the logging info related to
            # that specific run. At the end of the run the handler is removed.

            #time.sleep(1.0)

            stream = StringIO()
            streamhandler = logging.StreamHandler(stream)
            streamhandler.setLevel(logging.INFO)
            streamhandler.setFormatter(formatter)
            logger.addHandler(streamhandler)

            # Send a ping to the API to let it know we're alive. There is a two
            # second timeout on the request, but any exceptions are ignored. If
            # we are unable to send pings back to the API the error will be 
            # handled elsewhere.
            url = gems_api +"/worker/ping"
            try: r = requests.post(url, auth=gems_auth, data={'worker_uuid':worker_uuid}, timeout=5.0)
            except: pass
            
            # Reserve and parse the incoming job (Job Parsing)
            logger.info("[Worker %s] Waiting for a job!"%(worker_name))
            j = beanstalk.reserve(timeout=10)
            if j is None:
                continue

            try:
                logger.info("[Worker %s] Reserved a job..."%(worker_name))
                try:
                    logger.info("[Worker %s] JobChunk (...) Parsing Started."%(worker_name))
                    job = cPickle.loads(j.body)
                    jobchunk_uuid = job["uuid_jobchunk"]
                except Exception as e:
                    logger.info("[Worker %s] JobChunk (...) Parsing Failed."%(worker_name))
                    raise JobParseFailure("[Worker %s] Could not unpickle the job received from the message queue."%(worker_name))
                else:
                    logger.info("[Worker %s] JobChunk %s Parsing Completed."%(worker_name,jobchunk_uuid))

                # Set up the modelling framework (Job Processing)
                try:
                    status_code = 0
                    logger.info("[Worker %s] JobChunk %s Processing Started."%(worker_name,jobchunk_uuid))
                    model = GemFramework(job, gems_api=gems_api)
                    model.run()
                except Exception as e:
                    logger.info("[Worker %s] JobChunk %s Processing Failed."%(worker_name,jobchunk_uuid), exc_info=True)
                    raise JobProcessingFailure(e)
                else:
                    logger.info("[Worker %s] JobChunk %s Processing Completed."%(worker_name,jobchunk_uuid))
                

                # Report the results of the modelling job (Job Reporting)
                try:
                    logger.info("[Worker %s] JobChunk %s Reporting Started."%(worker_name,jobchunk_uuid))
                    logger.debug("[Worker %s] Maps package is approx: %.1f MB in size"%(worker_name,os.path.getsize(model._mapspackage) >> 20))
                    logger.info("[Worker %s] Posting maps package: %s"%(worker_name,model._mapspackage))
                    
                    files = {'package': open(model._mapspackage,'rb') }
                    data = {'jobchunk': job["uuid_jobchunk"], 'token':'-' }
                    status_code = 1                                    
                    url = gems_api + "/job/chunk/"+job["uuid_jobchunk"]+"/maps"
                    r = requests.post(url, auth=gems_auth, data=data, files=files)
                    r.raise_for_status() # Raises an exception when the status is not ok.

                except Exception as e:
                    logger.info("[Worker %s] JobChunk %s Reporting Failed."%(worker_name,jobchunk_uuid))
                    raise JobReportingFailure(e)

                else:
                    logger.info("[Worker %s] JobChunk %s Reporting Completed."%(worker_name,jobchunk_uuid))

            except (JobParseFailure, JobProcessingFailure, JobReportingFailure) as e:
                # Something went wrong trying to process this job.
                logger.critical("[Worker %s] A critical failure occurred while trying to process the job!"%(worker_name))
                logger.critical(e)
                status_code = -1

            except Exception as e:
                # An unexpected exception was raised. This should never really happen
                # because any exceptions should be caught by the JobParse, JobProcessing,
                # and JobReporting failures.
                logger.critical("[Worker %s] A critical (and unexpected) failure occurred while trying to process the job!"%(worker_name))
                logger.critical(e)
                status_code = -1

            else:
                # No exceptions were raised. Looking good!
                logger.info("[Worker %s] Everything went ok! Do cleanup by deleting the job from the queue and posting the logfile."%(worker_name))
                status_code = 1

            finally:
                #
                # Do cleanup after a model run or after an error occurred.
                #

                # Delete the job from the work queue
                try: 
                    j.delete()
                except:
                    logger.error("[Worker %s] Failed to delete job from work queue."%(worker_name))
                else:
                    logger.info("[Worker %s] Deleted job from queue."%(worker_name))

                # Flush the log stream of this model run and try to post it to the
                # API, that way we can view the logs of model runs in the browser.
                try:
                    url = gems_api +"/job/chunk/"+job["uuid_jobchunk"]
                    streamhandler.flush()
                    r = requests.post(url, auth=gems_auth, data={'log':stream.getvalue(),'status_code':status_code,'status_percentdone':100})
                    r.raise_for_status()
                except:
                    logger.debug("[Worker %s] Failed to post the final log file to the server."%(worker_name))
                else:
                    logger.debug("[Worker %s] Posted the logfile of this run to the server. "%(worker_name))
                finally:
                    logger.removeHandler(streamhandler) 

                logger.info("[Worker %s] All done! Look for another job!"%(worker_name))
            

    except Exception as e:
        # Something bad happened. 
        logger.critical("An unexpected exception occurred while running the job. Hint: %s. Deleting job from queue and exiting."%(e))
        sys.exit(1)

#def signal_handler(signal, frame):
#    print "Exiting gracefully!"
#    sys.exit(0)
#
#signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    #
    # Parse command line arguments
    #
    parser=argparse.ArgumentParser(description="Start a client to process models remotely")
    parser.add_argument("-p","--processes", help="Number of processes to start", default=1)
    parser.add_argument("-v","--verbose",   help="Log level", action='store_true',  default=True)
    parser.add_argument("-d","--directory", help="Working directory", default="/tmp/.gemsrundir")
    parser.add_argument("-a","--api",       help="Host name of the GEMS server where the work queue and API are running", default="localhost:88")
    parser.add_argument("-k","--apikey",    help="API username and key (admin:<key>)", required=True)
    parser.add_argument("-q","--queue",     help="Host name of the beanstalk work queue", default="localhost")
    parser.add_argument("-t","--tube",      help="Name of the beanstalk tube to use", default="gemsjobs")
    args = parser.parse_args()

    gems_api = "http://%s/api/v1"%(args.api)
    gems_auth = tuple(args.apikey.split(":"))
    gems_beanstalk = args.queue
    gems_tube = args.tube

    #
    # Check that the working directory exists and we can write to it.
    #
    try:
        if not os.path.isdir(args.directory):
            os.makedirs(args.directory)
        os.chdir(args.directory)
        tempfile = os.path.join(args.directory,"gems.txt")
        open(tempfile,'w')
        os.remove(tempfile)
    except Exception as e:
        print "Working directory %s is unsuitable. Check permissions. Hint: %s"%(args.directory,e)
        sys.exit(1)
    else:
        print "Working directory is %s"%(os.getcwd())

    
    #
    # Check connection to beanstalk server
    #
    try:
        beanstalk = beanstalkc.Connection(host=gems_beanstalk, port=11300)
        stats = beanstalk.stats()
        beanstalk.close()
    except Exception as e:
        print "Connection to work queue at %s:%d failed! Exiting!"%(gems_beanstalk, 11300)
        sys.exit(1)
    else:
        print "Beanstalk work queue found at %s:%d"%(gems_beanstalk, 11300)

    #
    # Check connection to API
    #
    try:
        r = requests.get(gems_api, auth=gems_auth)
        r.raise_for_status()
        response = r.json()
        if not response["authenticated"]:
            raise Exception("API could be contacted but authentication failed! Check your API username and access token.")
    except Exception as e:
        print "Connection to API at %s failed! Hint:%s"%(gems_api, e)
        sys.exit(1)
    else:
        print "GEMS API found and successfully authenticated at %s"%(gems_api)

#    try: 
#        num_processes = int(args.processes)
#    except: 
#        num_processes = 1
#    finally: 
#        print "Starting %d worker process(es)..."%(worker_name_processes)

    #
    # Create a UUID for this worker
    #
    worker_uuid = str(uuid.uuid4())

    print "*** STARTING GEMS CLIENT '%s' ***"%(worker_uuid)
    
    worker(worker_uuid, args, gems_api, gems_beanstalk, gems_auth, gems_tube)

    #
    # Start up the client
    #
#    print ""
#    jobs=[]
#    for i in range(num_processes):
#        p = multiprocessing.Process(target=process, args=(i, args, gems_api, gems_beanstalk, gems_auth, gems_tube))
#        jobs.append(p)
#        p.start()


