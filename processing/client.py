#!/usr/bin/env python

"""
Digital Earth Client
"""

import os
import sys
import argparse
import requests
import beanstalkc
import json
import multiprocessing
import uuid
import cPickle
import logging

from StringIO import StringIO

from gem.model import GemModel
from gem.framework import GemFramework

def process(num):
    #Set up logging
    logger=logging.getLogger()
    logger.setLevel(logging.DEBUG)  
    formatter=logging.Formatter('%(asctime)s %(levelname)s %(message)s')

    #Add a filehandler which writes to the log file
    filehandler=logging.FileHandler('/tmp/worker-%d.log'%(num))  
    filehandler.setLevel(logging.DEBUG)   
    filehandler.setFormatter(formatter)    
    logger.addHandler(filehandler)
    
    #Add a streamhandler for writing log output to stdout
    stdouthandler=logging.StreamHandler(sys.stdout)
    stdouthandler.setLevel(logging.DEBUG)
    stdouthandler.setFormatter(formatter)
    logger.addHandler(stdouthandler)
    
    try:
        beanstalk=beanstalkc.Connection(host=os.environ["DIGITALEARTH_BEANSTALK_SERVER"],port=11300)
        logger.info("[Worker %d] Connected to beanstalk message queue."%(num))
    except Exception as e:
        logger.critical("[Worker %d] Could not connect to beanstalk message queue at host '%s'"%(num,os.environ["DIGITALEARTH_BEANSTALK_SERVER"]))
    
    try:
        while True:
            #Add a streamhandler for writing log output to a StringIO which is
            #flushed after each model run to spit out the logging info related to
            #that specific run. At the end of the run the handler is removed.
            stream=StringIO()
            streamhandler=logging.StreamHandler(stream)
            streamhandler.setLevel(logging.DEBUG)
            streamhandler.setFormatter(formatter)
            logger.addHandler(streamhandler)
            
            # Reserve and parse the incoming job
            logger.info("[Worker %d] Waiting for a job!"%(num))
            j=beanstalk.reserve()            
            logger.info("[Worker %d] Reserved a job..."%(num))
            try:
                job = cPickle.loads(j.body)
                logger.info("[Worker %d] Job UUID: %s"%(num,job["uuid_chunk"]))
            except ValueError as e:
                logger.critical("[Worker %d] Could not unpickle the job received from the message queue."%(num))
                #hmm what to do? delete the job, go on to the next one?
                pass
            
            try:
                status_code = 0
                logger.info("[Worker %d] JobChunk UUID: %s"%(num,job["uuid_jobchunk"]))
                model=GemFramework(job)
                model.run()
                
                logger.debug("Timings overview:")
                for key in model._timings:
                    logger.debug("   %s: %.2fs"%(key,model._timings[key]))   
                                
                
                logger.debug("Maps package is approx: %.1f MB in size"%(os.path.getsize(model._mapspackage) >> 20))
                logger.info("[Worker %d] Posting maps package: %s"%(num,model._mapspackage))
                files={
                    'package':      open(model._mapspackage,'rb')            
                }
                data={
                    'jobchunk':     job["uuid_jobchunk"],
                    'token':        '-'
                }
                
                status_code = 1                
                
                
                url=os.environ["DIGITALEARTH_API"]+"/job/chunk/"+job["uuid_jobchunk"]+"/package"
                r=requests.post(url,data=data,files=files)
    
                if r.status_code==requests.codes.ok:            
                    logger.info("[Worker %d] Posting maps package successful! Returned status: %d"%(num,r.status_code))
                else:
                    logger.error("[Worker %d] Posting maps package failed! Returned status: %d"%(num,r.status_code))
    
            except Exception as e:
                logger.critical("An unexpected exception occurred during the model run! Hint: %s"%(e))
                status_code = -1
            finally:
                logger.info("[Worker %d] Delete job from beanstalk queue"%(num))
                j.delete()
                logger.info("[Worker %d] All done!"%(num))
                logger.info("[Worker %d] Completed the job with uuid: %s"%(num,job["uuid_jobchunk"]))
                url = os.environ["DIGITALEARTH_API"]+"/job/chunk/"+job["uuid_jobchunk"]+"/status"
                logger.debug("Posting logfile to: %s"%(url))
                streamhandler.flush()
                r = requests.post(url,data={'log':stream.getvalue(),'status_code':status_code,'status_percentdone':100})
                logger.removeHandler(streamhandler)
            
    except KeyboardInterrupt as e:
        # Cancelling the run script from the terminal
        logger.critical("Keyboard interrupt! Exiting!")
        sys.exit()
    except Exception as e:
        # Something bad happened. 
        logger.critical("An unexpected exception occurred while running the job. Hint: %s. Deleting job from queue and exiting."%(e))
        
        
        j.delete()
        sys.exit()



if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="Start a client to process models remotely")
    parser.add_argument("-p","--processes", action='store_true', help="Number of processes to start", default=1)
    parser.add_argument("-l","--loglevel", action='store_true', help="Log level", default=1)
    args = parser.parse_args()
    
    try: num_processes=int(args.processes)
    except: num_processes=1
    
    # For now, set num_processes to 1. Can't figure out how to do the logging
    # properly otherwise. The problem is that all the separate processed 
    # call a logget with getLogger() and then end up writing to the same log file,
    # even though we clearly need the logs of each individual process in a 
    # separate file.
    num_processes=1
 
    jobs=[]
    for i in range(num_processes):
        p=multiprocessing.Process(target=process,args=(i,))
        jobs.append(p)
        p.start()


