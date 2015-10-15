#!/usr/bin/env python

"""
Digital Earth Client
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

def process(num, args, gems_api, gems_beanstalk):
    #
    # Set up logging
    #
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

    #
    # Add a filehandler which writes to the log file
    #
    filehandler = logging.FileHandler('/tmp/worker-%d.log'%(num))  
    filehandler.setLevel(logging.DEBUG)   
    filehandler.setFormatter(formatter)    
    logger.addHandler(filehandler)
    
    #
    # Add a streamhandler for writing log output to stdout
    #
    stdouthandler = logging.StreamHandler(sys.stdout)
    stdouthandler.setLevel(logging.DEBUG)
    stdouthandler.setFormatter(formatter)
    logger.addHandler(stdouthandler)

    try:
        beanstalk = beanstalkc.Connection(host=gems_beanstalk, port=11300)
        logger.info("[Worker %d] Connected to beanstalk message queue."%(num))
    except Exception as e:
        logger.critical("[Worker %d] Could not connect to beanstalk work queue."%(num))
        sys.exit(1)

    try:
        while True:
            # Add a streamhandler for writing log output to a StringIO which is
            # flushed after each model run to spit out the logging info related to
            # that specific run. At the end of the run the handler is removed.

            time.sleep(1.0)

            stream = StringIO()
            streamhandler = logging.StreamHandler(stream)
            streamhandler.setLevel(logging.DEBUG)
            streamhandler.setFormatter(formatter)
            logger.addHandler(streamhandler)

            try:
                # Reserve and parse the incoming job (Job Parsing)
                logger.info("[Worker %d] Waiting for a job!"%(num))
                j = beanstalk.reserve()            
                logger.info("[Worker %d] Reserved a job..."%(num))

                try:
                    logger.info("[Worker %d] JobChunk (...) Parsing Started."%(num))
                    job = cPickle.loads(j.body)
                    jobchunk_uuid = job["uuid_jobchunk"]
                except Exception as e:
                    logger.info("[Worker %d] JobChunk (...) Parsing Failed."%(num))
                    raise JobParseFailure("[Worker %d] Could not unpickle the job received from the message queue."%(num))
                else:
                    logger.info("[Worker %d] JobChunk %s Parsing Completed."%(num,jobchunk_uuid))

                # Set up the modelling framework (Job Processing)
                try:
                    status_code = 0
                    logger.info("[Worker %d] JobChunk %s Processing Started."%(num,jobchunk_uuid))
                    model = GemFramework(job, gems_api=gems_api)
                    model.run()
                except Exception as e:
                    logger.info("[Worker %d] JobChunk %s Processing Failed."%(num,jobchunk_uuid))
                    raise JobProcessingFailure(e)
                else:
                    logger.info("[Worker %d] JobChunk %s Processing Completed."%(num,jobchunk_uuid))
                

                # Report the results of the modelling job (Job Reporting)
                try:
                    logger.info("[Worker %d] JobChunk %s Reporting Started."%(num,jobchunk_uuid))
                    logger.debug("[Worker %d] Maps package is approx: %.1f MB in size"%(num,os.path.getsize(model._mapspackage) >> 20))
                    logger.info("[Worker %d] Posting maps package: %s"%(num,model._mapspackage))
                    
                    files = {'package': open(model._mapspackage,'rb') }
                    data = {'jobchunk': job["uuid_jobchunk"], 'token':'-' }
                    status_code = 1                                    
                    url = gems_api + "/job/chunk/"+job["uuid_jobchunk"]+"/package"
                    r = requests.post(url, data=data, files=files)
                    r.raise_for_status() # Raises an exception when the status is not ok.

                except Exception as e:
                    logger.info("[Worker %d] JobChunk %s Reporting Failed."%(num,jobchunk_uuid))
                    raise JobReportingFailure(e)

                else:
                    logger.info("[Worker %d] JobChunk %s Reporting Completed."%(num,jobchunk_uuid))

            except (JobParseFailure, JobProcessingFailure, JobReportingFailure) as e:
                # Something went wrong trying to process this job.
                logger.critical("[Worker %d] A critical failure occurred while trying to process the job!"%(num))
                logger.critical(e)
                status_code = -1

            except Exception as e:
                # An unexpected exception was raised. This should never really happen
                # because any exceptions should be caught by the JobParse, JobProcessing,
                # and JobReporting failures.
                logger.critical("[Worker %d] A critical (and unexpected) failure occurred while trying to process the job!"%(num))
                logger.critical(e)
                status_code = -1

            else:
                # No exceptions were raised. Looking good!
                logger.info("[Worker %s] Everything went ok! Do cleanup by deleting the job from the queue and posting the logfile."%(num))
                status_code = 1

            finally:
                #
                # Do cleanup after a model run or after an error occurred.
                #

                # Delete the job from the work queue
                try: 
                    j.delete()
                except:
                    logger.error("[Worker %s] Failed to delete job from work queue."%(num))
                else:
                    logger.info("[Worker %s] Deleted job from queue."%(num))

                # Flush the log stream of this model run and try to post it to the
                # API, that way we can view the logs of model runs in the browser.
                try:
                    url = gems_api +"/job/chunk/"+job["uuid_jobchunk"]+"/status"
                    streamhandler.flush()
                    r = requests.post(url,data={'log':stream.getvalue(),'status_code':status_code,'status_percentdone':100})
                    r.raise_for_status()
                except:
                    logger.debug("[Worker %s] Failed to post the final log file to the server."%(num))
                else:
                    logger.debug("[Worker %s] Posted the logfile of this run to the server. "%(num))
                finally:
                    logger.removeHandler(streamhandler) 

                logger.info("[Worker %d] All done! Look for another job!"%(num))
            

    except Exception as e:
        # Something bad happened. 
        logger.critical("An unexpected exception occurred while running the job. Hint: %s. Deleting job from queue and exiting."%(e))
        sys.exit(1)

def signal_handler(signal, frame):
    print "Exiting gracefully!"
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    #
    # Parse command line arguments
    #
    parser=argparse.ArgumentParser(description="Start a client to process models remotely")
    parser.add_argument("-p","--processes", help="Number of processes to start", default=1)
    parser.add_argument("-v","--verbose",   help="Log level", action='store_true',  default=False)
    parser.add_argument("-d","--directory", help="Working directory", default="/tmp/gems")
    parser.add_argument("-a","--api",       help="Host name of the GEMS server where the work queue and API are running", default="localhost")
    parser.add_argument("-q","--queue",     help="Host name of the beanstalk work queue", default="localhost")
    args = parser.parse_args()

    gems_api = "http://%s/api/v1"%(args.api)
    gems_beanstalk = args.queue

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
        r = requests.get(gems_api)
        r.raise_for_status()
        if "hello" not in r.text:
            raise Exception("Received bad content from API, should contain the string 'hello'")
    except Exception as e:
        print "Connection to API at %s failed! Exiting!"%(gems_api)
        sys.exit(1)
    else:
        print "GEMS API found at %s"%(gems_api)

    try: 
        num_processes = int(args.processes)
    except: 
        num_processes = 1
    finally: 
        print "Starting %d worker process(es)..."%(num_processes)

    #
    # Start up the client
    #
    print ""
    jobs=[]
    for i in range(num_processes):
        p = multiprocessing.Process(target=process, args=(i, args, gems_api, gems_beanstalk))
        jobs.append(p)
        p.start()


