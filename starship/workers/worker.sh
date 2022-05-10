#!/bin/bash

# [START startup_script]

# Install python
sudo apt update
sudo apt install -y python3 python3-pip ffmpeg

# Install the dependencies
pip3 install absl-py requests google-cloud-storage youtube-dl
pip3 install --upgrade six
pip3 install --upgrade youtube-dl

# Download the youtube-dl repo, and patch the correct branch to fix the chapter extraction
# git clone https://github.com/ytdl-org/youtube-dl.git
# cd youtube-dl && git checkout bugfix/youtube/chapters-fix-extractor && pip3 install -e . && cd ..
# cd youtube-dl && pip3 install -e . && cd ..

# Use the metadata server to get the configuration specified during
# instance creation. Read more about metadata here:
# https://cloud.google.com/compute/docs/metadata#querying
INSTANCE_NAME=$(curl http://metadata/computeMetadata/v1/instance/attributes/iname -H "Metadata-Flavor: Google")
CS_BUCKET=$(curl http://metadata/computeMetadata/v1/instance/attributes/bucket -H "Metadata-Flavor: Google")
SERVER_IP=$(curl http://metadata/computeMetadata/v1/instance/attributes/serverip -H "Metadata-Flavor: Google")
FOLDER=$(curl http://metadata/computeMetadata/v1/instance/attributes/folder -H "Metadata-Flavor: Google")

# Fetch the server script
gsutil cp gs://$CS_BUCKET/worker.py worker.py

# Launch the server script
python3 worker.py --server_ip=$SERVER_IP --bucket=$CS_BUCKET --instance_name=$INSTANCE_NAME --folder=$FOLDER

# [END startup_script]
