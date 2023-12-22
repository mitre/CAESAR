#!/bin/python3

"""
Name: Docker Login
Description: Checks for existing docker login, if not found it logs into the private Docker Repo
Exit Codes:
  1 - ARTIFACTORY_PASSWORD environment variable not set
  2 - `docker login` command failed
"""

import json
import logging
import os
import subprocess
import sys

ARTIFACTORY_USERNAME = os.getenv("ARTIFACTORY_USERNAME", "dokazy")
DOCKER_CONFIG_PATH = os.getenv("DOCKER_CONFIG_PATH", "/root/.docker/config.json")
REGISTRY = os.getenv("REGISTRY", "artifacts.mitre.org:8200")

print("docker-login.py - Starting")

if not os.getenv("ARTIFACTORY_PASSWORD"):
  print("The environment variable ARTIFACTORY_PASSWORD is not set and is required, exiting")
  sys.exit(1)

dockerConfig = {}

# Try to open the docker config file
try:
  with open(DOCKER_CONFIG_PATH) as dockerConfigFile:
    dockerConfig = json.load(dockerConfigFile)
  
  # Check if already logged into the Docker Repo, if so exit
  if dockerConfig["auths"] and REGISTRY in dockerConfig["auths"]:
    print("Already authenticated, skipping login")
    sys.exit()
  
  print(f"Not logged into Docker Repo, attempting to login to {REGISTRY}")
except FileNotFoundError:
  print(f"Could not find the docker config file at {DOCKER_CONFIG_PATH}, continuing")
except:
  logging.exception('')
  print(f"There was an unexpected error trying to access the Docker config, trying to continue")

output = subprocess.run(f"echo $ARTIFACTORY_PASSWORD | docker login -u {ARTIFACTORY_USERNAME} --password-stdin {REGISTRY}", shell=True, encoding='UTF-8', capture_output=True)
  
# Make sure the command was successful
if output.returncode != 0:
  print(f"Docker Login to {REGISTRY} failed.\nstderr={output.stderr}")
  sys.exit(2)

print(f"Successfully logged into {REGISTRY}")
sys.exit()
