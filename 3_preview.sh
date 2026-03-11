#!/bin/bash

PORT=8001
DIR="/home/gideon/nxflo_00"

echo ""
echo "Starting preview server..."
echo ""
echo "Preview URL:"
echo "http://www.nxflo.com:${PORT}/"
echo ""

cd "$DIR"

python3 -m http.server $PORT
