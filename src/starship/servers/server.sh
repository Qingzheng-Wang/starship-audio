#!/bin/bash

# [START startup_script]

# Install python
sudo apt update
sudo apt install -y python3 python3-pip

# Install the dependencies
pip3 install flask absl-py requests APScheduler

# Use the metadata server to get the configuration specified during
# instance creation. Read more about metadata here:
# https://cloud.google.com/compute/docs/metadata#querying
INSTANCE_NAME=$(curl http://metadata/computeMetadata/v1/instance/attributes/iname -H "Metadata-Flavor: Google")
CS_BUCKET=$(curl http://metadata/computeMetadata/v1/instance/attributes/bucket -H "Metadata-Flavor: Google")

# Fetch the server script
gsutil cp gs://$CS_BUCKET/server.py server.py
gsutil cp gs://$CS_BUCKET/videos.json videos.json

# Launch the server script
python3 server.py

# [END startup_script]
