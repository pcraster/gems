###############################################################################
### GEMS Configuration Settings
###############################################################################
import os

###############################################################################
### Copy the following parameters into a local_settings.py file. Do not fill
### sensitive information in the settings.py file.
###############################################################################
DEBUG = True 
MAIL_FROM_EMAIL =           ''
SECRET_KEY =                ''
HOME=                       '/var/wwwdata/gems'
CODE=                       '/var/www/gems'
SQLALCHEMY_DATABASE_URI =   'postgresql://gems@/gemsdb'

GEONAMES_API_USERNAME=      'kokoalberti'
MAPDELIVERY_URL=            ''
ADMIN_NAME=                 'administrator'
ADMIN_EMAIL=                'admininstrator@example.org'

MAPSERVER_URL=              'http://127.0.0.1/cgi-bin/mapserv'
MAPSERVER_POSTGIS_CONNECT=  'dbname=gemsdb user=gems password= host='
#Mapserver executable is used to check the installed mapserver version using
#mapserv -v
MAPSERVER_EXECUTABLE=       '/opt/mapserver/bin/mapserv'

#Valid values frin 0-5. See mapserver documentation for more info. Any 
#mapserver debug info is logged to the apache error_log file. Be aware that 
#setting this to 5 will cause a LOT of log output (for each map tile, this adds 
#up quicly.
MAPSERVER_DEBUG=            5

###############################################################################
### End Local Settings
###############################################################################


###############################################################################
### Other Settings (you shouldn't have to change these)
###############################################################################
BEANSTALK_HOST=             'localhost'
BEANSTALK_PORT=             11300


TEMP =                      os.path.join(HOME, "tmp")
BCRYPT_LEVEL =              12

###############################################################################
### Settings for the Flask-User Extension
###############################################################################
USER_PRODUCT_NAME           = "GEMS"
USER_ENABLE_USERNAME        = True
USER_ENABLE_EMAIL           = True
USER_LOGIN_TEMPLATE         = 'flask_user/login.html'
USER_REGISTER_TEMPLATE      = 'flask_user/register.html'
USER_AFTER_LOGIN_ENDPOINT   = 'site.home'
USER_AFTER_LOGOUT_ENDPOINT   = 'site.home'
USER_AFTER_CONFIRM_ENDPOINT = 'site.home'

USER_ENABLE_REGISTRATION       = True
USER_ENABLE_CONFIRM_EMAIL   = False 
USER_ENABLE_CHANGE_USERNAME = False

USER_ENABLE_FORGOT_PASSWORD    = False 
USER_SEND_PASSWORD_CHANGED_EMAIL = False
USER_SEND_REGISTERED_EMAIL = False
USER_SEND_USERNAME_CHANGED_EMAIL = False

USER_CHANGE_PASSWORD_URL      = '/user/change-password'
USER_CHANGE_USERNAME_URL      = '/user/change-username'
USER_CONFIRM_EMAIL_URL        = '/user/confirm-email/<token>'
USER_EMAIL_ACTION_URL         = '/user/email/<id>/<action>'
USER_FORGOT_PASSWORD_URL      = '/user/forgot-password'
USER_LOGIN_URL                = '/user/login'
USER_LOGOUT_URL               = '/user/logout'
USER_MANAGE_EMAILS_URL        = '/user/manage-emails'
USER_REGISTER_URL             = '/user/register'
USER_RESEND_CONFIRM_EMAIL_URL = '/user/resend-confirm-email'
USER_RESET_PASSWORD_URL       = '/user/reset-password/<token>'


###############################################################################
### End Configuration
###############################################################################

#
# Application Configuration Settings
#
#WCS={
#   'uu-wcs':            'http://localhost/cgi-bin/mapserv?map=/var/mapserver/wcs.map',
#   'turbo':             'http://turbo.geo.uu.nl/cgi-bin/mapserv?MAP=/data/projectdata/globaldata/globaldata.map'
#}
#UTILS={
#   'python':            '/usr/bin/python',
#   'tar':               '/bin/tar',
#   'lz4':               '/opt/lz4/lz4c',
#   'mapserv':           '/usr/lib/cgi-bin/mapserv',
#   'psql':              '/usr/bin/psql',
#   'gdalinfo':          '/usr/bin/gdalinfo',
#   'gdal_translate':    '/usr/bin/gdal_translate',
#   'gdallocationinfo':  '/usr/bin/gdallocationinfo',
#   'gdalbuildvrt':      '/usr/bin/gdalbuildvrt',
#   'gdaltindex':        '/usr/bin/gdaltindex',
#   'gdalwarp':          '/usr/bin/gdalwarp',
#   'gdaladdo':          '/usr/bin/gdaladdo',
#   'gdal_edit':         '/usr/bin/gdal_edit.py',
#   'gdal_fillnodata':   '/usr/bin/gdal_fillnodata.py',
#   'pgsql2shp':         '/usr/bin/pgsql2shp'
#}
#MODULES=[
#   'beanstalkc',
#   'gdal',
#   'pcraster',
#   'yaml',
#   'json',
#   'psycopg2',
#   'requests',
#   'slugify',
#   'subprocess',
#   'banana',
#   'hashlib'
#]
#BEANSTALK={
#   'host':              '127.0.0.1',
#   'port':              11300,
#   'tube_statusupdates':'status',
#   'tube_process':      'process',
#   'tube_seed':         'seeding'
#}




