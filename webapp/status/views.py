import os
import re
import subprocess
import uuid
import json

from . import status

from flask import g, current_app, render_template, request, jsonify, make_response, flash
from datetime import datetime, timedelta

from ..models import *

@status.route('')
def home():
    """
    
    Todo:
    
    - status of beanstalk queue rather than entire server
    - mappsever status
    - databsae status
    - mapserver connect
    
    """
    status = gems_system_status()
    
    
    
    connected = False
    
    if beanstalk:
        connected = True
        stats = beanstalk.queue.stats()
    else:
        stats = {}
    
    return render_template("status/status.html", status=status, stats=stats, connected=connected)