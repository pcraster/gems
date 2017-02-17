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
    return render_template("status/status.html", beanstalk=beanstalk)