#Set some required environment variables and start the client. You may
#have to modify these to match your environment.

export DIGITALEARTH_HOME="/var/digitalearth"
export DIGITALEARTH_BEANSTALK_SERVER="localhost"
export DIGITALEARTH_PCRASTER="/home/koko/pcraster/pcraster-4.0.2_x86-64/python"
export DIGITALEARTH_API="http://localhost:5000/api/v1"
export DIGITALEARTH_RUNDIR="/var/digitalearth/tmp/run"

/usr/bin/python client.py
