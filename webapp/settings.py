###############################################################################
### Flask Configuration Settings
###############################################################################
import os

BCRYPT_LEVEL = 12

###############################################################################
### Copy the following parameters into a local_settings.py file. Do not fill
### sensitive information in the settings.py file.
###############################################################################
DEBUG = False 
MAIL_FROM_EMAIL =           ''
SECRET_KEY =                ''
HOME=                       '/var/wwwdata/gems'
CODE=                       '/var/www/gems'

SQLALCHEMY_DATABASE_URI =   'postgresql://gems@/gemsdb'
MAPSERVER_URL=              'http://127.0.0.1/cgi-bin/mapserv'
GEONAMES_API_USERNAME=      'kokoalberti'
MAPDELIVERY_URL=            ''

###############################################################################
### End Local Settings
###############################################################################


#not used at the moment.
BEANSTALK_HOST=             'localhost'
BEANSTALK_PORT=             11300


TEMP = os.path.join(HOME, "tmp")

#
# Application Configuration Settings
#
WCS={
   'uu-wcs':            'http://localhost/cgi-bin/mapserv?map=/var/mapserver/wcs.map',
   'turbo':             'http://turbo.geo.uu.nl/cgi-bin/mapserv?MAP=/data/projectdata/globaldata/globaldata.map'
}
UTILS={
   'python':            '/usr/bin/python',
   'tar':               '/bin/tar',
   'lz4':               '/opt/lz4/lz4c',
   'mapserv':           '/usr/lib/cgi-bin/mapserv',
   'psql':              '/usr/bin/psql',
   'gdalinfo':          '/usr/bin/gdalinfo',
   'gdal_translate':    '/usr/bin/gdal_translate',
   'gdallocationinfo':  '/usr/bin/gdallocationinfo',
   'gdalbuildvrt':      '/usr/bin/gdalbuildvrt',
   'gdaltindex':        '/usr/bin/gdaltindex',
   'gdalwarp':          '/usr/bin/gdalwarp',
   'gdaladdo':          '/usr/bin/gdaladdo',
   'gdal_edit':         '/usr/bin/gdal_edit.py',
   'gdal_fillnodata':   '/usr/bin/gdal_fillnodata.py',
   'pgsql2shp':         '/usr/bin/pgsql2shp'
}
MODULES=[
   'beanstalkc',
   'gdal',
   'pcraster',
   'yaml',
   'json',
   'psycopg2',
   'requests',
   'slugify',
   'subprocess',
   'banana',
   'hashlib'
]
BEANSTALK={
   'host':              '127.0.0.1',
   'port':              11300,
   'tube_statusupdates':'status',
   'tube_process':      'process',
   'tube_seed':         'seeding'
}


# Configure Flask-User
USER_PRODUCT_NAME           = "Virtual Globe"     # Used by email templates
USER_ENABLE_USERNAME        = True              # Register and Login with username
USER_ENABLE_EMAIL           = False              # Register and Login with email
USER_LOGIN_TEMPLATE         = 'flask_user/login.html'
USER_REGISTER_TEMPLATE      = 'flask_user/login_or_register.html'
USER_AFTER_LOGIN_ENDPOINT   = 'site.home'
USER_AFTER_LOGOUT_ENDPOINT   = 'site.home'
USER_AFTER_CONFIRM_ENDPOINT = 'site.home'

USER_ENABLE_CONFIRM_EMAIL   = False 
USER_ENABLE_CHANGE_USERNAME = False
USER_ENABLE_REGISTRATION       = False
USER_ENABLE_FORGOT_PASSWORD    = False 
USER_ENABLE_EMAIL = False
USER_SEND_PASSWORD_CHANGED_EMAIL = False
USER_SEND_REGISTERED_EMAIL = False
USER_SEND_USERNAME_CHANGED_EMAIL = False


# URLs                        # Default
USER_CHANGE_PASSWORD_URL      = '/user/change-password'
USER_CHANGE_USERNAME_URL      = '/user/change-username'
USER_CONFIRM_EMAIL_URL        = '/user/confirm-email/<token>'
USER_EMAIL_ACTION_URL         = '/user/email/<id>/<action>'     # v0.5.1 and up
USER_FORGOT_PASSWORD_URL      = '/user/forgot-password'
USER_LOGIN_URL                = '/user/login'
USER_LOGOUT_URL               = '/user/logout'
USER_MANAGE_EMAILS_URL        = '/user/manage-emails'
USER_REGISTER_URL             = '/user/register'
USER_RESEND_CONFIRM_EMAIL_URL = '/user/resend-confirm-email'    # v0.5.0 and up
USER_RESET_PASSWORD_URL       = '/user/reset-password/<token>'

