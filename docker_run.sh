#! /bin/bash

docker run -d --name ganyu \
    -v $(pwd)/settings.json:/app/settings.json \
    -v $(pwd)/ganyu.db:/app/ganyu.db \
    ganyu
