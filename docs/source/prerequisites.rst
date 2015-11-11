Prerequisites
=============

Software
--------

* Python 2.7
* PostgreSQL 9.4
* PostGIS 2.0
* Mapserver 7.0
* Beanstalkd 1.10
* GDAL 1.11
* Apache 2.4.6
* PCRaster 4.1

All these requirements can be installed relatively easily using CentOS packages, except Mapserver and Beanstalkd, which we will compile ourselves, and PCRaster which can be downloaded as compiled binaries.

Python Modules
--------------
See requirements.txt in the GEMS repository.

Hardware
--------

While the hardware requirements are not fixed it is recommended to have, for the application server, at least:

* 4GB RAM
* 4 cores
* 1TB disk space

The worker machines which process the model may be run on the same machine, in which case you might have to beef it up a little. Otherwise, for worker machines the following specs are recommended:

* 1GB RAM
* 1 core
* 5GB disk space
* Fast network connectivity and throughput to the application server, as well as any other servers where input maps are fetched from.



