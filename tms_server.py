import json
import logging
import os
from functools import lru_cache

import humanize
import math
import psutil
import requests
from flask import Flask, Response, request
from pyproj import Transformer
from werkzeug.exceptions import HTTPException, InternalServerError, NotFound

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)


# TODO
# - rate limiter
# - https
# - s3
# - flag to enable debug
# - flag to set port (or env var?)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    logging.error(f"unknown path: '{path}'")
    logging.warning(f"Unknown Request: '{request}'")
    logging.warning(f"Unknown Headers: '{request.headers}'")
    logging.warning(f"Unknown Body: '{request.get_data()}'")
    return Response(status=404)


def tile_to_lat_lon(zoom, xtile, ytile):
    n = 2.0 ** int(zoom)
    lon_deg = int(xtile) / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * int(ytile) / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


@app.route("/health")
def health():
    return Response(status=200)


@app.route("/info")
def info():
    pid = os.getpid()
    process = psutil.Process()
    process.cpu_percent()
    mem_info = process.memory_info()._asdict()
    # make readable
    mem_info['mem'] = humanize.naturalsize(mem_info['rss'])
    data = {
        "cpu_usage": process.cpu_percent(interval=0.1),
        "mem_info": mem_info,
        "cache": get_tile.cache_info()._asdict(),
        "available_maps": map_to_raster_func,  # TODO make this more legible
    }
    return Response(json.dumps(data), status=200)


@app.route("/<type>/<map>/<zoom>/<xtile>/<ytile>.png")
def tilemap(type, map, zoom, xtile, ytile):
    zoom, xtile, ytile = int(zoom), int(xtile), int(ytile)

    try:
        tile = get_tile(type, map, zoom, xtile, ytile)
        headers = {"content-type": "image/jpeg"}
        return Response(tile, status=200, headers=headers)
    except Exception as e:
        if not isinstance(e, HTTPException):
            e = InternalServerError(e)
        logging.error(repr(e))
        return Response(repr(e), status=e.code)


# based on testing, average tile size was 8KB
avg_tile_size = 1 << 13

# max ram is 512MB
max_ram = 1 << 29

# max cache size based on max ram and average item size
cache_size = int(max_ram / avg_tile_size)


@lru_cache(maxsize=cache_size)
def get_tile(type, map, zoom, xtile, ytile):
    ul_lat, ul_lon = tile_to_lat_lon(zoom, xtile, ytile)
    br_lat, br_lon = tile_to_lat_lon(zoom, xtile + 1, ytile + 1)
    img = get_image(type, map, ul_lat, ul_lon, br_lat, br_lon)

    logging.debug(f"cache miss {zoom}/{xtile}/{ytile}; size: {len(img)}")

    return img


# national map services:
# https://apps.nationalmap.gov/services/
# 3DEPElevation names from here:
# https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/rasterFunctionInfos
map_to_raster_func = {
    "3dep_elevation": {
        "hillshade_gray": "Hillshade Gray",
        "aspect_degrees": "Aspect Degrees",
        "aspect_map": "Aspect Map",
        "contour_25": "Contour 25",
        "hillshade_elevation_tinted": "Hillshade Elevation Tinted",
        "height_ellipsoidal": "Height Ellipsoidal",
        "greyhillshade_elevationfill": "GreyHillshade_elevationFill",
        "hillshade_multidirectional": "Hillshade Multidirectional",
        "slope_map": "Slope Map",
        "slope_degrees": "Slope Degrees",
        "contour_smoothed_25": "Contour Smoothed 25",
    }
}


def get_image(type, map, ul_lat, ul_lon, br_lat, br_lon):
    if type not in map_to_raster_func:
        raise NotFound(f"map type '{type} not found")

    maps = map_to_raster_func.get(type)

    if map not in maps:
        raise NotFound(f"map '{map} not found")

    raster_func = maps.get(map)

    # National Map request seemed to ask for EPSG:102100, which is apparently
    # deprecated, but similar to 3857. So we use 4326 as a good degrees based
    # SRS to convert degrees to meters in 3857
    logging.debug(f"degrees: {ul_lon}, {ul_lat}, {br_lon}, {br_lat}")
    transformer = Transformer.from_crs("epsg:4326", "epsg:3857", always_xy=True)
    ul_x, ul_y = transformer.transform(xx=ul_lon, yy=ul_lat)
    br_x, br_y = transformer.transform(xx=br_lon, yy=br_lat)
    logging.debug(f"meters: {ul_x}, {ul_y}, {br_x}, {br_y}")
    params = {
        'f': 'image',
        'bandIds': '',
        'renderingRule': json.dumps({"rasterFunction": raster_func}),
        # example
        # 'bbox': "-8375600.976190533,5097202.303121362,-8224561.4082989665,5196723.3139487",
        'bbox': f"{ul_x},{br_y},{br_x},{ul_y}",
        'imageSR': 102100,
        'bboxSR': 102100,
    }
    url = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        e = HTTPException(str(resp.content))
        e.code = resp.status_code
        raise e

    return resp.content


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=53214, )
