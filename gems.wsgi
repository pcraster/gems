#
# This is the WSGI configuration file for the GEMS application.
#
# For testing purposes like setting up mod_wsgi in apache it 
# may be useful to have a test application which just says 
# "hello world. In that case comment out the line "from webapp 
# import app as application" and define your own dummy application
# like in the commented out section below that.
#

import sys
sys.path.insert(0, '/var/www/gems')

from webapp import app as application

#
#def application(environ, start_response):
#    status = '200 OK'
#    output = 'Hello World!'
#    response_headers = [('Content-type', 'text/plain'),
#                        ('Content-Length', str(len(output)))]
#    start_response(status, response_headers)
#    return [output]
#
