Data Model
==========

Discretization
--------------

A **Discretization** is also known as a chunkscheme, a naming convention 
left over from the old GEMS application. The GEMS application needs to 
divide the world up into smaller managable sections so that the 
geographical extent of the model run can be constrained. After all, 
running a model on a grid with millions of rows and columns would be 
incredibly slow as well as contain a lot of area which the user may not be 
interested in. We therefore divide the world up into small chunks that 
represent the model area. These chunks can be any shape: for example 
1 by 1 degree tiles, river catchments, countries, provinces, or some other 
arbitrary shape which can be defined by a polygon. A particular collection 
of these chunks is called a "Discretization". 

Several default discretizations are created upon installation of GEMS, 
such as "world_onedegree" at 100m resolution, meaning the Chunks of one by
one degree, with a cell size of 100m. An overview of the discretizations
which are active in GEMS can be found if you log in as an admin and 
select "Discretizations" in the admin sidebar.

Once a discretization is created, it should not be modified because doing
do so could influence the model results, as data generated after a 
discretization is changed can then no longer be compared to data created
before the changes.

Discretizations are described in the SQLAlchemy data model by the 
``Discretization`` class in ``models.py``.

.. autoclass:: webapp.models.Discretization
    :members:
    :special-members:

        :return test test: Return val
            
        :return: A new Discretization instance.
        :rtype: Discretization

Chunk
-----

A **Chunk** is a single modelling unit which must be part of a 
Discretization (chunkscheme). For example, the ``world_onedegree_100m`` 
discretization contains nearly 14000 chunks dispersed all over the world. 
When a model run is requested, the system checks which chunks in the 
desired chunkscheme fall within the requested model run extent. A modelling 
job (with custom parameters) is then started for each of the individual 
chunks.


.. autoclass:: webapp.models.Chunk
    :members:
    :special-members:

Map
---

.. autoclass:: webapp.models.Map
    :members:
    :special-members:

Model
-----

.. autoclass:: webapp.models.Model
    :members:
    :special-members: