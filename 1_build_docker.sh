#!/bin/bash
set -euo pipefail

docker build -f Dockerfile.portal -t nxflo-portal-api:latest .
docker build -t nxflo-static:latest .
