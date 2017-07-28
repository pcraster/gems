Installation
============

This is the installation manual which describes installing GEMS on CentOS 7.1.

Introduction
------------

This section describes the installation of the GEMS web application on a vanilla out of the box CentOS 7.1 server. Most commands will require root access, so using sudo is recommended. We use CentOS 7.1 because 6.x uses an old Python version 2.6.x, which gives a lot of problems further down the line. Unfortunately the ELGIS repository does not provide packages for CentOS 7, but between the EPEL and PostgreSQL repositories for Centos 7 we have relatively recent versions of many geospatial tools. The only things we need to compile manually are mapserver and beanstalkd, but compiling these is relatively effortless once all the prerequisite development packages have been installed.

This installation manual is quite detailed, and you may be able to skip some steps if certain things are already installed on your target machine. Unfortunately it is quite a long install procedure because GEMS uses a lot of other software (GDAL, Mapserver, PostGIS, Beanstalkd, etc.) and it is therefore not as easy as copying everything over and clicking install.

System
------------

First update the system:

.. code-block:: none

    yum update

Install development tools:

.. code-block:: none

    yum groupinstall development

Install the EPEL repository:

.. code-block:: none

    yum install epel-release

Install some Python necessities::

    yum install python-devel python-crypto py-bcrypt python-pip python-requests PyYAML pyOpenSSL

Install geospatial tools and a bunch of other packages we want to use::

    yum install gdal gdal-devel gdal-libs gdal-python geos geos-devel proj proj-devel proj-epsg proj-nad freetype freetype-devel libpng libpng-devel gd gd-devel zlib-devel openssl openssl-devel bzip2-devel python-psycopg2 giflib giflib-devel libxml2 libxml2-devel fgci fcgi-devel curl libcurl libcurl-devel net-tools wget cmake httpd httpd-devel mod_wsgi htop sqlite sqlite-devel python-sqlite3dbm nmap

Disable Security Enhanced Linux by editing ``/etc/sysconfig/selinux`` and setting::

    SELINUX=disabled

.. warning::

    Disabling SELinux makes the system more permissive (at the expense of security) but saves a lot of time debugging why certain things in a webapp aren't working, such as strange memory errors in Shapely (for more info see `this link <http://stackoverflow.com/questions/27045407/python-2-7-rhel-6-5-shapely-1-4-4-memoryerror>`_) or certain permissions that may be denied to the webapp. 

.. note:: 

    Reboot the machine after disabling SELinux.

Create a user on the system which will own the Apache, Beanstalk, and worker processes later::

    adduser gems -s /sbin/nologin

Apache
------

Apache should have been installed in the above steps in the ``httpd`` and ``httpd-devel`` packages. Enable (so it starts at boot) and start the service::

    systemctl enable httpd
    systemctl start httpd

And open the firewall to allow connections on port 80::

    sudo firewall-cmd --permanent –add-port=80/tcp
    sudo firewall-cmd --reload

PostgreSQL and PostGIS
----------------------
Check out the `YUM installation of PostgreSQL <https://wiki.postgresql.org/wiki/YUM_Installation>`_ for more information. 

Configure the yum repository by editing the file ``/etc/yum.repos.d/CentOS-Base.repo`` and adding ``exclude=postgresql*`` to the ``[base]`` and ``[updates]`` sections of the file.

Install the RPM file containing PostgreSQL and PostGIS::

    yum localinstall http://yum.postgresql.org/9.4/redhat/rhel-7-x86_64/pgdg-centos94-9.4-1.noarch.rpm

Install the PostgreSQL packages::

    yum install postgresql94-server postgresql94-contrib postgresql94-python

Initialize the database in ``/var/lib/pgsql/9.4/data`` by initializing the service::

    /usr/pgsql-9.4/bin/postgresql94-setup initdb

Install PostGIS::

    yum install postgis2_94 postgis2_94-devel 

And start the service. It runs on port ``5432`` by default. We don't need to open this port in the firewall because we only connect to it locally::

    systemctl enable postgresql-9.4
    systemctl start postgresql-9.4

.. note:: 

    If you'd like to connect to this database remotely, for example using a graphical SQL client, you will need to open port 5432 as well as set the appropriate permissions in ``/var/lib/pgsql/9.4/data/pg_hba.conf``.

    Todo: Add a short description of how to do this. Open the port and enable passwd authentication on remote hosts.

Mapserver
---------

Unfortunately there are no mapserver packages available for Centos 7, so we will compile this ourselves and install it in ``/opt/mapserver``. Download and extract the sources::

    wget http://download.osgeo.org/mapserver/mapserver-7.0.0.tar.gz
    tar -zxvf mapserver-7.0.0.tar.gz
    cd mapserver-7.0.0
    mkdir build
    cd build

Use ``cmake`` to configure the build::

    cmake -DCMAKE_INSTALL_PREFIX=/opt/mapserver -D"CMAKE_PREFIX_PATH=/usr/pgsql-9.4;/usr;/usr/bin;/opt" -DWITH_POSTGIS=ON -DWITH_CLIENT_WFS=ON -DWITH_CLIENT_WMS=ON -DWITH_CURL=ON -DWITH_SOS=ON -DWITH_PHP=OFF -DWITH_PYTHON=OFF -DWITH_HARFBUZZ=OFF -DWITH_CAIRO=OFF -DWITH_FRIBIDI=OFF -DWITH_SVGCAIRO=OFF -DWITH_ORACLESPATIAL=OFF -DWITH_MSSQL2008=OFF -DWITH_SDE=OFF ..

Compile and install into ``/opt/mapserver``::

    make
    make install

Verify that everything works by running ``/opt/mapserver/bin/mapserv -v``, which should return something along the lines of::

    MapServer version 7.0.0 OUTPUT=PNG OUTPUT=JPEG SUPPORTS=PROJ SUPPORTS=AGG SUPPORTS=FREETYPE SUPPORTS=ICONV SUPPORTS=WMS_SERVER SUPPORTS=WMS_CLIENT SUPPORTS=WFS_SERVER SUPPORTS=WFS_CLIENT SUPPORTS=WCS_SERVER SUPPORTS=SOS_SERVER SUPPORTS=FASTCGI SUPPORTS=GEOS INPUT=JPEG INPUT=POSTGIS INPUT=OGR INPUT=GDAL INPUT=SHAPEFILE

.. warning::

    Make sure WMS_SERVER and WCS_SERVER are supported, and that inputs POSTGIS, OGR, SHAPEFILE, and GDAL are present.

    If PostGIS can't be found, check that the CMAKE_PREFIX_PATH in the cmake command is correct. 

.. note:: 

    GEMS uses Mapserver version 7.0. Some of the directives for filtering maps changed from Mapserver 6.4 to 7.0 (it now uses ``PROCESSING`` instead of ``FILTER``, see the `Mapserver migration guide <http://mapserver.org/MIGRATION_GUIDE.html#migration>`_ for more info). GEMS uses these filters for filtering on particular config keys and attribute names in tile indexes, so this is crucial in serving or displaying the correct maps. The templates do try and correct this when you user Mapserver 6.x, but it's better just to stick with 7.0.


Beanstalkd
----------
Download and extract the tarball::

    wget https://github.com/kr/beanstalkd/archive/v1.10.tar.gz
    tar -zxvf v1.10.tar.gz
    cd beanstalkd-1.10

Compile and install::

    make
    make install PREFIX=/opt/beanstalkd

We want to use systemd to run the beanstalkd service. There is a service file already in the GEMS repository, so just link that file from the systemd services directory::

    ln -s /var/www/gems/data/systemd/beanstalk.service /etc/systemd/system/beanstalk.service

Verify that the contents of the file don't need to be changed (for example the user to run the installation as). Use the ``systemctl`` command to enable, start, and status the service::

	systemctl enable beanstalk
	systemctl start beanstalk
	systemctl status beanstalk

PCRaster
--------
Download::

    wget http://downloads.sourceforge.net/project/pcraster/PCRaster/4.1.0/pcraster-4.1.0_x86-64.tar.gz 

Extract into ``/opt/pcraster-4.1.0_x86-64``::

    tar -zxvf pcraster-4.1.0_x86-64.tar.gz -C /opt

Create a link so that PCRaster is accessible via ``/opt/pcraster``::

	ln -s /opt/pcraster-4.1.0_x86-64 /opt/pcraster

Create the file ``/usr/lib/python2.7/site-packages/pcraster.pth`` and add the PCRaster Python path::

    /opt/pcraster/python

And check that it can be imported without problems::

    python
    Python 2.7.5 (default, Jun 24 2015, 00:41:19) 
    (...)
    >>> from pcraster.framework import *
    >>> 

GEMS Web Application
--------------------

Now that the server environment and software is set up, we can install the web application and get everything up and running. We will use the following directories:

* The **application directory** will be ``/var/www/gems``
* The **data directory** will be ``/var/wwwdata/gems``

You can use different ones if you want, but remember to update any paths you need to set to the correct locations.

.. warning::

    These two directories must be different! The application directory stores all the web application code, and the data directory stores all the data. The installation script that you will run later will delete everything in the data directory, so choose it carefully.

Getting started
+++++++++++++++

Create the data and application directories::

    mkdir -p /var/wwwdata/gems
    mkdir -p /var/www/gems

And change the ownership to the ``gems`` user::

    chown -R gems:users /var/wwwdata/gems
    chown -R gems:users /var/www/gems

Clone the application
+++++++++++++++++++++
Clone the repository into the the application directory::

    Todo.

Install the required python modules::

    pip install -r /var/www/gems/requirements.txt

Create the file ``/usr/lib/python2.7/site-packages/gems.pth`` and add the path to the GEMS processing modules::

    /var/www/gems/processing

And check that they can be imported without any problems::

    python 
    Python 2.7.5 (default, Jun 24 2015, 00:41:19) 
    (...)
    >>> from gem.model import * 
    >>> 

Database setup
++++++++++++++
While the database server is installed, we still need to set up a database that GEMS can use as well as enable PostGIS. First switch to the ``postgres`` user for superuser access to the database::

    sudo -u postgres -iH

Create a database user ``gems`` and press ENTER twice for no password::

    createuser -SdRP gems

Create a database ``gemsdb`` of which the user ``gems`` is the owner::

    createdb -E UTF8 -O gems gemsdb

Enable the PostGIS extension on the database::

    /usr/pgsql-9.4/bin/psql gemsdb -c "CREATE extension postgis;"

Verify that it works and that geos, proj, and GDAL are found::

    /usr/pgsql-9.4/bin/psql gemsdb -c "SELECT PostGIS_full_version();"
    (...)
    POSTGIS="2.1.8 r13780" GEOS="3.4.2-CAPI-1.8.2 r3921" PROJ="Rel. 4.8.0, 6 March 2012" GDAL="GDAL 1.11.1, released 2014/09/24" LIBXML="2.7.6" LIBJSON="UNKNOWN" RASTER

And exit the postgres user shell::

    exit

Configure the database so that it trusts local UNIX domain socket connections by editing the PostgreSQL config file ``/var/lib/pgsql/9.4/data/pg_hba.conf``, and change the following lines::

    # "local" is for Unix domain socket connections only 
    local   all             all                      peer 

To::

    # "local" is for Unix domain socket connections only 
    local   all             all                      trust 

.. warning::

    Be aware that this now trusts **all** socket connections coming from the local machine, giving them full access to the database. Nothing from the outside should be able to connect to our database directly anyway, so it's good to disable connections from the outside alltogether at the firewall level. 

    Todo: enable trust authent only on gemsdb and add a password.

Restart the PostgreSQL service::

    systemctl restart postgresql-9.4

You should now be able to connect to the database on a local socket::

    /usr/pgsql-9.4/bin/psql 'postgresql://gems@/gemsdb'
    psql (9.4.4) 
    Type "help" for help. 
    
    Gemsdb=> \q #to quit

Configuration
+++++++++++++

Open the ``/var/www/gems/webapp/settings.py`` file and copy the configuration section at the top to a local settings file ``/var/www/gems/webapp/local_settings.py``. This local settings file is not included in the repository and allows you to override any settings specific to a local machine.

Generate a secret random key using openssl (or if you prefer another method that should also work fine with the command ``openssl rand -base64 32``. Copy the random string into the ``SECRET_KEY`` parameter in the ``local_settings.py`` file.

Correct the other entries in the ``local_settings.py`` file like your e-mail address or database login, if that uses a different database location.

Flask includes a development server which you can use to quickly test if the application loads ok and there are no modules missing before you get it set up on a proper webserver::

	cd /var/www/gems
    ./manage.py runserver
    (...)
    * Running on http://127.0.0.1:5000/


Webserver
+++++++++
Now that the application is set up, we need to make it accessible to the web using a proper webserver. GEMS uses the WSGI standard to serve the application via a web server, in this case Apache. It also possible to use other web servers such as nginx, but we'll stick to Apache for now. We will host GEMS in an Apache virtual host.

First verify that the paths in the WSGI file ``/var/www/gems/gems.wsgi`` are correct.

There is a virtual host include file in ``~/data/apache/gems.conf``. Link this to the 
Apache configuration directory so that it will be loaded automatically when Apache starts::

    todo

Verify that the application and data directories are owned by the Apache user::

    chown -R gems:users /var/www/gems
    chown -R gems:users /var/wwwdata/gems

Open the configuration file ``/etc/httpd/conf.d/gems.conf`` and correct the ``ServerName`` directive to match your server name, as well as the user and group items of the ``WSGIDaemonProcess`` directive. The user and group must match the user and group owners of the ``/var/www/gems`` and ``/var/wwwdata/gems`` directories. In our case the user is ``gems`` and the group is ``users``.

Restart Apache::

    systemctl restart httpd

To get Apache to reload the application (without restarting the whole server) after you've made some changes or deployed a new version, just ``touch``ing the ``gems.wsgi`` file will also work::

    touch /var/www/gems/gems.wsgi

You should now see a login screen when you browse to your server. There is a status page that will give some additional information about the status of the application. It can be found at ``http://<ServerName>/status``.

Verify that the mapserver CGI script can be executed by pointing your browser at ``http://<ServerName>/cgi-bin/mapserv``. It should return an error about ``QUERY_STRING`` being empty.


Initialization
++++++++++++++
The web application is now up and running, but it does not have users of any data yet. This initialization takes place via a web interface. This will create the necessary data folders, create the tables in the database, add some users, add chunkschemes, and upload some default models you can play with. Point a modern browser at ``http://<ServerName>/install`` and click the install button. Please be patient as it may take a while to initialize everything. If an error occurs it will generally give some debug information about what went wrong. Fix it, reload the page, and click the button again.

Once the application has been installed, the install link described above will be invalidated so that you can't do a new installation while there is still another one present. If you want to do a reinstall anyway (reset to factory settings as it were) then manually remove the ``./install/install-ok.txt``file in the data directory. Once this file has been removed you can visit the install link again. 

.. warning::

	Removing the ``./install/install-ok.txt`` file in the data directory and running the reinstalling script **WILL DELETE ALL DATA IN THE WEB APPLICATION!**
	To delete temporary data from the webapplication run the data cleanup script in the GEMS manage.py file with ``./manage.py data_cleanup``.

.. notice::

    If for whatever reason the installation stalls without producing an error, you also will not be able to restart it, as the system will think there is still an installation happening, and it will not allow two installs to run at once. Manually remove the lockfile ``/tmp/install-running.txt`` and try again.

GEMS Workers
------------

Processing of model runs in the GEMS architecture is done by workers which need to be started separately from the web application. Technically speaking, workers are pretty basic scripts that process any jobs which are posted to the beanstalk work queue, and send the model outputs back to the web application. Workers can be started on the same machine as the web application, but also on multiple other machines which are connected by network to the web application, that way the machine running the web application will not suffer from the load of having to process all these PCRaster models. The worker nodes monitor the work queue for messages (on port 11300) and post results via HTTP to the GEMS API (on port 80). Make sure there is solid network connectivity between worker nodes and the GEMS web application. The client application for the workers is located in the GEMS application in the subdirectory ``processing``.

We first do a test run of the worker script to verify that everything works properly::

    cd /var/www/gems/processing
    ./client.py --directory /tmp/.gemstest --api localhost --queue localhost
    Working directory is /tmp/.gemstest 
    Beanstalk work queue found at localhost:11300 
    GEMS API found at http://localhost/api/v1 
    Starting 1 worker process(es)... 
    
    2015-10-12 12:31:11,677 INFO [Worker 0] Connected to beanstalk message queue. 
    2015-10-12 12:31:12,678 INFO [Worker 0] Waiting for a job!

Press ``CTRL-C`` to kill it and fix any errors that may occur.

We use systemd to launch these workers as a processing service, much in the same way that we created a service for beanstalkd. Link the service file in the application directory to the systemd service directory::

    ln -s /var/www/gems/data/systemd/gemsworker.service /etc/systemd/system/gemsworker.service

Open the service file and make sure that the ``ExecStart`` command uses the same arguments as in the test case before. In case your workers are on a difference machine you will need to update the arguments to the ``client.py`` script so that the client is able to find and access the work queue and the API::

    ExecStart=/var/www/gems/processing/client.py --api localhost --queue localhost --directory /tmp/.gemsrundir

Enable the service so it starts after reboot::

    systemctl enable gemsworker

Start the service::

	systemctl start gemsworker

Check that the service is running properly::

    systemctl status gemsworker

Testing
-------

Troubleshooting
---------------



