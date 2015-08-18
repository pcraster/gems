# -*- coding: utf-8 -*-
"""
Some standalone utility functions which can be used throughout the app.
"""

import hashlib
import math
import datetime

def create_configuration_key(params):
    """
    This hashing function is used for creating configuration hashes
    which are used to determine if one model configuration is the
    same as another one. A string is constructed in the following 
    manner:

    <param_key>=<param_value>,<param_key>=<param_value> (...)

    For each parameter passed in params. The list of params is sorted
    alphabetically. This string is then hashed and returned. Now, 
    when another user, session, or whatever, runs the model with the
    same parameterset, this function is executed and it will return 
    the same key as last time.
    """
    excluded_config_keys = ["bbox","model_name"]

    param_list = []
    parameters = {}
    for k,v in sorted(params.items()):
        if k not in excluded_config_keys:
            parameters.update({k:v})
            param_list.append("%s=%s"%(str(k),str(v)))
    
    cleartext_key=",".join(param_list)
    
    return hashlib.md5(cleartext_key).hexdigest(),cleartext_key,parameters

def parsetime(timestring, round_to=-3600, offset=0):
    """
    Parses model start time. If it cannot parse the start time from a string
    with the format %Y-%m-%dT%H:%M:%S it will assume now is the start. This
    leaves some options open to use other keywords like 'now' or 'yesterday'.
    
    The time can be rounded up or down a number of seconds by respectively
    using a positive or negative integer as the round_to argument. 
    
    The time (after rounding) can be offset by a number of seconds, the offset
    is applied to the rounded date.
    """
    try:
        epoch = datetime.datetime.strptime(timestring,"%Y-%m-%dT%H:%M:%S")
    except:
        epoch = datetime.datetime.utcnow()

    rounded = round_datetime(dt=epoch,seconds=round_to)
    offset = rounded+datetime.timedelta(seconds=offset)
    return offset
    
def round_datetime(dt=datetime.datetime.now(), seconds=-3600):
    seconds_base = int(round((dt-dt.min).total_seconds()))
    return dt.min+datetime.timedelta(seconds=round_to(seconds_base,seconds))
    
def round_to(number,roundto):
    return ((number//abs(roundto))*abs(roundto))+max(0,roundto)
    
