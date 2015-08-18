import os
import re
import subprocess
import uuid
import json

from . import status

from flask import g, current_app, render_template, request, jsonify, make_response, flash
from datetime import datetime, timedelta

from ..models import *

#
# The status page is a separate view to prevent errors elsewhere from being
# able to view the status page. You should always be able to visit the 
# status page to check out why something isn't working.
#

@status.route('')
def home():
	return render_template("status/status.html")
 

@status.route('/job/<uuid:job_uuid>',methods=["GET"])
def job_status(job_uuid):
    job=Job.query.filter_by(uuid=job_uuid.hex).first_or_404()
    jobchunks=job.jobchunks.all()
    return render_template("status/job.html",job=job)

@status.route('/config')
def config():
	"""
	Shows information on the site configuration
	"""
	for module in current_app.config["MODULES"]:
		try: 
			__import__(module)
			flash("Imported module <code>%s</code>."%(module),"ok")
		except Exception as e:
			flash("Could not import module <code>%s</code>. Hint: %s"%(module,e),"error")

	for key, value in current_app.config["UTILS"].iteritems():
		if os.path.isfile(value) and os.access(value, os.X_OK):
			flash("Utility program <code>%s</code> found and is executable."%(value),"ok")
		else:
			flash("Utility program <code>%s</code> was not found or is not executable!"%(value),"error")
	return render_template("status.html")