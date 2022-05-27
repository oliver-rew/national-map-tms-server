#!/bin/bash

docker rm -f map-server || true 2>&1 > /dev/null
docker run --pull always --name map-server --rm -d -p 53214:53214 oliverrew/map-server:dev
