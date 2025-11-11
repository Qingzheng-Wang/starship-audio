#!/bin/bash

# [START startup_script]
# Startup script for audio-only worker
# This script downloads audio from YouTube in original format

# Install python and dependencies
sudo apt update
sudo apt install -y python3 python3-pip ffmpeg

# Install the required Python packages
pip3 install absl-py requests google-cloud-storage yt-dlp

# Use the metadata server to get the configuration specified during
# instance creation. Read more about metadata here:
# https://cloud.google.com/compute/docs/metadata#querying
INSTANCE_NAME=$(curl http://metadata/computeMetadata/v1/instance/attributes/iname -H "Metadata-Flavor: Google")
CS_BUCKET=$(curl http://metadata/computeMetadata/v1/instance/attributes/bucket -H "Metadata-Flavor: Google")
SERVER_IP=$(curl http://metadata/computeMetadata/v1/instance/attributes/serverip -H "Metadata-Flavor: Google")
FOLDER=$(curl http://metadata/computeMetadata/v1/instance/attributes/folder -H "Metadata-Flavor: Google")
GCLOUD_PROJECT=$(curl http://metadata/computeMetadata/v1/project/project-id -H "Metadata-Flavor: Google")

# Fetch the audio worker script from GCP bucket
gsutil cp gs://$CS_BUCKET/worker_audio_only.py worker_audio_only.py

# Launch the audio worker script
python3 worker_audio_only.py \
    --server_ip=$SERVER_IP \
    --bucket=$CS_BUCKET \
    --instance_name=$INSTANCE_NAME \
    --folder=$FOLDER \
    --save_original=True

# [END startup_script]

