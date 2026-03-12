#!/bin/bash

set -e

CONTAINER=nxflo-static
IMAGE=nxflo-static:latest
PORT=9001

echo "Stopping old container (if exists)..."
docker stop $CONTAINER 2>/dev/null || true

echo "Removing old container (if exists)..."
docker rm $CONTAINER 2>/dev/null || true

echo "Starting new container..."
docker run -d \
  --name $CONTAINER \
  -p ${PORT}:80 \
  --restart unless-stopped \
  $IMAGE

echo ""
echo "Deployment complete"
echo "Production URL:"
echo "https://www.nxflo.com"
