#!/bin/sh

set -eu

# Echo out build info for debugging
echo "CI_JOB_ID=$CI_JOB_ID"
echo "CI_COMMIT_SHA=$CI_COMMIT_SHA"

if timeout 60 wget -q -O /tmp/install_certs.sh --no-check-certificate https://gitlab.mitre.org/mitre-scripts/mitre-pki/raw/master/os_scripts/install_certs.sh 2>/dev/null;
then sh /tmp/install_certs.sh && rm -f /tmp/install_certs.sh; 
else echo "Not on the MII, skipping certificate install"; 
fi

echo "Installing python, curl, and bash"
apk add --no-cache curl python3 bash

# Make sure pip is installed
python3 -m ensurepip --upgrade

# Install requests and urllib3 modules for fetch commit
python3 -m pip install requests urllib3

echo "Making sure Docker Login is valid"
python3 bin/ci-cd/docker-login.py
