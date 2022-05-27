from flask import Flask, Response, request
import logging
import math
from pyproj import Transformer, Proj, transform
import requests

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)


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


@app.route("/<zoom>/<xtile>/<ytile>.png")
def tilemap(zoom, xtile, ytile):
    zoom, xtile, ytile = int(zoom), int(xtile), int(ytile)

    tile = get_tile(zoom, xtile, ytile)
    headers = {
        "content-type": "image/jpeg"
    }
    return Response(tile, status=200, headers=headers)


cache = {}


def get_tile(zoom, xtile, ytile):
    if cache.get((zoom, xtile, ytile,)):
        logging.info(f"cache hit {zoom}/{xtile}/{ytile}")
        return cache.get((zoom, xtile, ytile,))

    logging.info(f"cache miss {zoom}/{xtile}/{ytile}")
    ul_lat, ul_lon = tile_to_lat_lon(zoom, xtile, ytile)
    br_lat, br_lon = tile_to_lat_lon(zoom, xtile + 1, ytile + 1)
    img = get_image(ul_lat, ul_lon, br_lat, br_lon)
    cache[(zoom, xtile, ytile,)] = img
    return img


def get_image(ul_lat, ul_lon, br_lat, br_lon):
    # National Map request seemed to ask for EPSG:102100, which is apparently
    # deprecated, but similar to 3857. So we use 4326 as a good degrees based
    # SRS to convert degrees to meters in 3857
    logging.info(f"degrees: {ul_lon}, {ul_lat}, {br_lon}, {br_lat}")
    transformer = Transformer.from_crs("epsg:4326", "epsg:3857", always_xy=True)
    ul_x, ul_y = transformer.transform(xx=ul_lon, yy=ul_lat)
    br_x, br_y = transformer.transform(xx=br_lon, yy=br_lat)
    logging.info(f"meters: {ul_x}, {ul_y}, {br_x}, {br_y}")
    params = {
        'f': 'image',
        'bandIds': '',
        'renderingRule': '{"rasterFunction":"Hillshade Elevation Tinted"}',
        # example
        # 'bbox': "-8375600.976190533,5097202.303121362,-8224561.4082989665,5196723.3139487",
        'bbox': f"{ul_x},{br_y},{br_x},{ul_y}",
        'imageSR': 102100,
        'bboxSR': 102100,
    }
    url = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
    resp = requests.get(url, params=params)
    return resp.content


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=53214, debug=True)
