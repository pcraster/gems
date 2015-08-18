#Todo:
# - data provider for local files
# - pass a list of directories (or a globbable string like *.tif) to look for files accessible with GDAL
# - read the files, make them available as layers so users can do: self.readmap('filename.tif')
# - will then read and reproject a the chunked data from that file
#
#
#
#
# Data provider for local 'data buckets'. Users can upload a file (raster, vector) to their
# data bucket, which is accessible via local.<username>.<bucketname>
#
# Alternative is to upload data to a WCS or WFS and use the respective providers
# for those two.