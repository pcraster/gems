GEMS Web Application
====================

Structure
---------

Management
---------
In order to delete temporary data from the GEMS web application, run the command ``./manage.py data_cleanup`` from the gems folder on the webserver. This will delete all maps, jobs, jobchunks and all data associated with these, without touching the models or the users.