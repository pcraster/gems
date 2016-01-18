API
===

GEMS uses a RESTful HTTP API. The API allows HTTP clients to request model runs or the status of a model run. Most likely the client will be the GEMS web application itself, but it is also possible to access the API using a command line client like `curl <http://curl.haxx.se/>`_ or using the excellent Python `requests <http://docs.python-requests.org/en/latest/>`_ HTTP library.

.. contents::
   :depth: 2
   :local:

Current version
---------------
The current version of the GEMS API is ``v1``. The API is available at ``http://<hostname>/api/v1/``. To test whether you can access the API use a ``curl`` command::

    $ curl --user <username>:<your_token_here> http://<hostname>/api/v1/
    {
        "authenticated": true, 
        "hello": "world", 
        "message": "Welcome to the GEMS API!", 
        "status": true
    }

If a 200 OK is returned the service is operating normally. Check the ``authenticated`` attribute of the JSON response to see whether your authentication succeeded.


Authentication
--------------
Current authentication implementation uses `HTTP basic access authentication <https://en.wikipedia.org/wiki/Basic_access_authentication>`_ in the form of a username and an API token as a substitute for a password. If the server is not running on SSL this is rather useless, but seeing as GEMS is still very much a project in development we will leave it for the time being. Also, using a token that cannot be used to log in to the application, rather than the user's actual password, is a slightly better alternative. Views in the API blueprint can be updated to require token authentication by adding the ``@requires_auth_token`` decorator. This will check the provided token/password against the user's ``api_token`` property. If they match, access is granted, otherwise a status 403 Unauthorized is returned. The code for handling the basic authentication is located at the top of the API views.

.. warning::

    Todo: warning about risks of not using SSL

Status codes
------------
The GEMS API aims to return appropriate `HTTP status codes <http://en.wikipedia.org/wiki/List_of_HTTP_status_codes>`_ for every request. Successful requests will be in the 2XX or 3XX range, whereas errors of all sorts will be in the 4XX range for client errors, and 5XX for server errors. When an error does occur it will be accompanied by a JSON message which might give an indication of what went wrong, looking something like::

    HTTP/1.1 400 Bad Request
    (...)
    Content-Type: application/json

    {
        'message': 'Your job is too big!'
    }

Depending on the circumstances there may also be other fields in the JSON object, for example a job id or extra attribute with more information about the exception that occurred. Note that different endpoints can return different status codes, but that all endpoints may return codes like 503 Service Unavailable in case the API service is down or not available, or a 404 Not Found in case the resource is not found.

Some API requests may also return content types other than JSON, but these are exceptions to the rule. In the cases where this is relevant (for example in `webapp.api.views.model_status`_) it will be mentioned explicitly.

The following HTTP status codes are used in the GEMS API. Their approximate meaning is explained as well, but can be different depending on the API call you're making.

**200 OK**

Your request was successful! Congratulations!

**304 Not Modified**

Nothing new to return. Could also be used for something which is in the cache.

**404 Not Found**

The resource was not found. This can occur when you're requesting details of a processing job which does not exist, or when you try to access an endpoint which is not defined.

Methods
-------
Only HTTP POST and GET methods are used in the GEMS API. GET methods are used when requesting information and should generally not change any variables or state on the server side. POST requests are used for updating and creating resources.

PUT, PATCH, or HEAD methods are not used at this time.

Endpoints
---------
The API endpoints are coded as view functions in the API blueprint of the Flask application. The views can be found in ``./webapp/api/views.py``. The routing decorator in Flask is used to specify the URL format and specifies allowed request methods to that specific view. Any URLs described below need to have ``/api/v1`` prepended. The following endpoints are defined and mapped to views:

==========================================================  ===============================  ==========================
URL                                                         Methods                          Endpoint
==========================================================  ===============================  ==========================
``/``				                                        GET                              `webapp.api.views.home`_
``/job``                                                    POST                             `webapp.api.views.job_create`_
``/job``                                                    GET                              `webapp.api.views.job_prognosis`_
``/job/<job_uuid>``                                         GET, POST                        `webapp.api.views.job_status`_
``/job/chunk/<jobchunk_uuid>``                              GET, POST                        `webapp.api.views.jobchunk_status`_
``/job/chunk/<jobchunk_uuid>/log``                          GET                              `webapp.api.views.jobchunk_log`_
``/job/chunk/<jobchunk_uuid>/maps``                         GET, POST                        `webapp.api.views.jobchunk_maps`_
``/config/<config_key>``                                    GET                              `webapp.api.views.config_status`_
``/model/<model_name>``                                     GET, POST                        `webapp.api.views.model_status`_
``/discretization/<discr_name>/bounds``                     GET                              `webapp.api.views.discretization_bounds`_
``/discretization/<discr_name>/coverage.json``              GET                              `webapp.api.views.discretization_coverage`_
==========================================================  ===============================  ==========================

Views
-----

.. autofunction:: webapp.api.views.home

.. autofunction:: webapp.api.views.job_prognosis

.. autofunction:: webapp.api.views.job_create

.. autofunction:: webapp.api.views.job_status

.. autofunction:: webapp.api.views.jobchunk_status

.. autofunction:: webapp.api.views.jobchunk_log

.. autofunction:: webapp.api.views.jobchunk_maps

.. autofunction:: webapp.api.views.config_status

.. autofunction:: webapp.api.views.model_status

.. autofunction:: webapp.api.views.discretization_bounds

.. autofunction:: webapp.api.views.discretization_coverage

.. autofunction:: webapp.api.views.worker_ping

