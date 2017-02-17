import os
import re
import subprocess
import uuid
import json
import tarfile
import datetime
import hashlib
import imghdr 

import StringIO

from PIL import Image, ImageDraw

from . import data

from flask import g, current_app, render_template, request, jsonify, make_response, Response, send_from_directory, send_file
from datetime import datetime, timedelta

import requests

from ..models import *

def last_modified(filename):
    """
    Returns a last modified time of a file. If the file doesnt exist it returns
    a date far in the past so that we can still compare dates.
    """
    try:
        t = os.path.getmtime(filename)
        return datetime.datetime.fromtimestamp(t)
    except:
        return datetime.datetime(1982, 5, 15, 0, 0, 0)
        
def serve_from_cache(timestamp_cache,timestamp_list):
    """
    Returns False if any of the timestamps in timestamp_list are before the 
    timestamp given in timestamp_cache.
    """
    for t in timestamp_list:
        if timestamp_cache < t:
            return False
    return True

@data.route('/mapserver')    
def mapserver():
    """
    
     This blueprint view is a mapserver wms proxy+cache. The web application
     requests tiles from this blueprint instead of straight from 
     mapserver. If a locally cached tile does not exist, the request
     is forwarded to mapserver and the response tile (image) is 
     stored locally and at the same time streamed to the client. 
     If a tile does exist, we check two things:
    
     - the date of the model's mapserver .map file
     - the modified date of the maps in the tileindex (map table in postgis)
       to check if any new maps have been created in the bbox of the wms
       request.
    
     If any of these two dates are newer than the cached image tile
     we request it again from mapserver and cache the new version. 
     This should greatly speed up any repeated requests. Furthermore
     we may even be able to build it some load balancing or do some
     other stuff to the image tiles before sending them back.
    
     Another advantage is that when serving static files using Flask's
     send_from_directory() eTag values are added in the request, which
     allows the browser to cache the file locally as well. In those
     cases no data needs to be transferred from the client.
     
     Todo: - verify that the image coming back from the backend server is
             a valid image. if it's not, don't cache it and return something
             like a png with a red cross in it.
             I don't think you can count on the http status codes coming out
             of mapserver either for this, because when an error occurs it
             returns 200 regardless along with some XML error messagfe. maybe
             the mimetype or something can help.
           - print some sort of error message in failed images

    
    """
    cache_key_cleartext="%s:%s:%s:%s"%(request.values.get("BBOX"),request.values.get("CONFIGKEY"),request.values.get("LAYERS"),request.values.get("TIME"))
    cache_key=hashlib.md5(cache_key_cleartext).hexdigest()
    cache_dir=os.path.join(current_app.config["HOME"],"tilecache",cache_key[0:2],cache_key[2:4])
    cache_file=os.path.join(cache_dir,cache_key+".png")
    cache_timestamp=last_modified(cache_file)
    
    empty_file=os.path.join(current_app.config["HOME"],"tilecache","empty.png")
    error_file=os.path.join(current_app.config["HOME"],"tilecache","error.png")
    
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)
    
    #
    # hits is a list of all the map filenames (.vrt files) that were found
    # within <geom> as defined by the bbox and other params like configkey,
    # layers, and time. If hits is 0 then obviously there are no maps, so
    # there is no point in bothering mapserver about it (it and the apache
    # instance its running on have enough to do) so just return an empty png.
    #
    geom=from_shape(box(*map(float,request.values.get("BBOX").split(","))),3857)
    hits=Map.query.filter(
        Map.geom_web_mercator.intersects(geom),
        Map.config_key==request.values.get("CONFIGKEY"),
        Map.attribute==request.values.get("LAYERS"),
        Map.timestamp==request.values.get("TIME")
    ).with_entities(Map.filename).all()
    
    #
    # source_timestamps should contain a list of the timestamps
    # of the mapserver .map file, as well as all the source files
    # referred to in the "filename" field of the "Map" table.
    #
    if len(hits)==0:
        print "No hits found for this map"
        if not os.path.isfile(empty_file):
            im = Image.new("RGBA", (512, 512))
            im.save(empty_file)
        return send_file(empty_file)
    else:
        print "Found %d hits"%(len(hits))

    #
    # so it looks like we got some hits, compile a list of timestamps
    # of the source files so we can compare them
    #
    source_timestamps=[last_modified(request.values.get("MAP"))]
    for filename in [r[0] for r in hits]:
        source_timestamps.append(last_modified(filename))
    
    if not serve_from_cache(cache_timestamp,source_timestamps):
        #
        # Ok so perhaps we don't always want to stream the image straight to
        # the client, since if an error occurs on the upstream end we prefer 
        # to return an error image with a red cross. We can't tell if the
        # image contains errors until it's been loaded all the way and we've
        # verified it using imghdr.what(). Also, using flask's send_file()
        # the first time will set the right cache headers, meaning that the
        # file can be cached by the browser as well.
        #
        stream=StringIO.StringIO()
        url=current_app.config.get("MAPSERVER_URL")+"?"+request.query_string
        r=requests.get(url, stream=True)
        print "fetching from backend: %s"%(url)
        if r.ok:
            for chunk in r.iter_content(1024):
                stream.write(chunk)
            imgdata=stream.getvalue()
            imgtype=imghdr.what('',h=imgdata)
            if imgtype=='png':
                f=open(cache_file,'w')
                f.write(imgdata)
                f.close()
                return send_file(cache_file)
                
        #
        # if we arrive here it means we have some sort of error, either the 
        # status code returned was not ok, or the type of content returned
        # was not an image. to let the client know something is wrong, send
        # an image with a big red cross in it.
        #
        if not os.path.isfile(error_file):
            im = Image.new("RGBA", (512, 512))
            draw = ImageDraw.Draw(im)
            draw.line((0, 0) + im.size, fill=(255,0,0), width=2)
            draw.line((0, im.size[1], im.size[0], 0), fill=(255,0,0),width=2)
            del draw
            im.save(error_file,'PNG')
        
        return send_file(error_file)
    else:
        print "serving from cache!~"
        return send_file(cache_file)
        
@data.route('/download')    
def download():
    """
    Todo    
    
    View for downloading source data. This should take more or less the same
    arguments/query string params as a WCS getcoverage request. However, rather
    than relaying this request live to the backend mapserver application, this
    view will perform the request, save the source file locally, and make the
    download available under a short url:
    
    /data/download/xosaf49
    
    Which then serves the geotiff right from disk.
    
    """
    pass

@data.route('/tile')
def tile():
    """
    Todo
    
    View for creating custom tiles. This could perform a WCS request to fetch
    the source data in TIF format, and then colorize the tile on the fly before
    sending it back to the user. The user interface can be adapted to allow
    in depth exploration of the data, for example by customizing the min and 
    max values, or showing only data within a specified range or class.
    
    """
    pass

@data.route('/point')
def point():
    """
    View for serving a json encoded file with point data which is used for 
    generating charts. Using regular getfeatureinfo requests with mapserver is
    already a pain in the ass (http://augusttown.blogspot.nl/2010/01/customize-wms-getfeatureinfo-response.html)
    let alone also supporting TIME and a config key, and returning data in json. 
    
    It will be easier to just build this ourselves and return a nice json array 
    of the attribute values at a particular location. It will also be superfast 
    if we use GDAL getlocationinfo to query the pixel value at all timesteps 
    (=all bands) of the .tif file in one go, rather than read from the individual 
    .vrt files which each represent one timestep.
    
    Additionally it's possible to include other data in the response that is
    useful for plotting the data, such as a JavaScript timestamp equivalent (ms
    since epoch) as well as the limits of the y axis, which should correspond
    with those on the legend colorscale.
    
    
    """
    rounding=4
    
    lat = float(request.values.get("lat"))
    lng = float(request.values.get("lng"))
    configkey = request.values.get("configkey","")
    layer = request.values.get("layers")    
    time = request.values.get("time")    
    
    geom = from_shape(Point(lng,lat),4326)
    
    modelconfig = ModelConfiguration.query.filter_by(key=configkey).first_or_404()
    
    hits=db.session.query(Map).join(Chunk).filter(
        Map.geom.intersects(geom),
        Map.config_key == configkey,
        Map.attribute == layer,
    ).with_entities(Chunk.uuid).group_by(Chunk.uuid).first()
    
    if (hits != None):
        try:
            #get the reporting information for this model attribute
            reporting = modelconfig.model.reporting.get(layer)            
            
            chunkkey=hits[0]
            #Extract a list of timestamps
            times = db.session.query(Map).join(Chunk).filter(
                Map.geom.intersects(geom),
                Map.config_key == configkey,
                Map.attribute == layer
            ).with_entities(Map.timestamp).order_by(Map.timestamp).all()            
            timestamps = [t[0].isoformat() for t in times]     
            
            
            #So we have identified a chunk uuid from the Map table for which there
            #are some maps present. Now we very simply check if the source file is 
            #present on the file system:
            #
            # /var/digitalearth/maps/<configkey>/<chunkkey>/<layer>/<layer>.tif
            #
            #If that file exists, query it using getlocationinfo, that should give
            #us an attribute value for each timestep which corresponds with the 
            #list of timestaps generated earlier.
            
            sourcefile = os.path.join(current_app.config["HOME"],"maps",configkey[0:2],configkey[2:4],configkey,chunkkey[0:2],chunkkey[2:4],chunkkey,layer,layer+".tif")
            p=subprocess.Popen(["/usr/bin/gdallocationinfo","-wgs84","-valonly",sourcefile,str(lng), str(lat)], stdout=subprocess.PIPE)
            stdout, err = p.communicate()
            values = [round(v, rounding) for v in map(float,stdout.split())]
            current_value=values[timestamps.index(time)]
            
            print "modelparameters:"
            print reporting['symbolizer']['values']
                        
            
            yaxis = {
                'min':reporting['symbolizer']['values'][0],
                'max':reporting['symbolizer']['values'][1]
            }

            return jsonify(currentvalue=current_value, value=values,timestamp=timestamps,model=modelconfig.model.name,yaxis=yaxis),200
        except Exception as e:
            return jsonify(currentvalue=undefined, value=[],timestamp=[],message="Error:%s"%(e)),500
    return jsonify(currentvalue=undefined, value=[],timestamp=[],message="No data found"),200
        
    
    