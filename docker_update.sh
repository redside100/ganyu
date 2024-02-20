#! /bin/bash
git pull
git submodule update
docker build -t ganyu .
./docker_restart.sh
