#!/bin/bash

docker run -d \
  --name nxflo-static \
  -p 9001:80 \
  --restart unless-stopped \
  nxflo-static:latest
