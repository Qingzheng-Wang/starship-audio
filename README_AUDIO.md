# Starship Audio Download - LAION-DISCO-12M

This guide explains how to use the improved Starship system to download audio from the LAION-DISCO-12M dataset. The system has been enhanced to preserve original audio formats, including bit depth, channels, sample rate, and codec information.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Setup](#setup)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Advanced Options](#advanced-options)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Overview

The Starship audio download system is designed to:

1. **Preserve Original Audio Quality**: Downloads audio in its original format without re-encoding
2. **Parallel Processing**: Uses multiple GCP workers to download thousands of audio files simultaneously
3. **Metadata Preservation**: Saves comprehensive metadata including audio specs and LAION-DISCO annotations
4. **Robust Error Handling**: Implements retries and timeout mechanisms for reliability

### What's Preserved

- **Format**: Original container format (webm, m4a, opus, etc.)
- **Codec**: Original audio codec (opus, aac, mp3, vorbis, etc.)
- **Bit Depth**: Original bit depth
- **Sample Rate**: Original sample rate (Hz)
- **Channels**: Original channel configuration (mono, stereo, surround, etc.)
- **Bitrate**: Original bitrate (kbps)

## Architecture

```
┌─────────────────────┐
│  LAION-DISCO-12M    │
│  Parquet Files      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ prepare_laion_      │
│ disco_input.py      │
│ (Converts to JSON)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Chunked JSON       │
│  Input Files        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  app_audio.py       │
│  (Main orchestrator)│
└──────────┬──────────┘
           │
           ├──────────────────────────────┐
           ▼                              ▼
┌─────────────────────┐       ┌─────────────────────┐
│  Server Instance    │◄──────┤  Worker Instances   │
│  (Task Distributor) │       │  (Audio Downloaders)│
└──────────┬──────────┘       └──────────┬──────────┘
           │                              │
           └──────────────┬───────────────┘
                          ▼
                 ┌─────────────────────┐
                 │   GCP Bucket        │
                 │   (Audio Files +    │
                 │    Metadata)        │
                 └─────────────────────┘
```

## Setup

### Prerequisites

1. **GCP Account**: You need a GCP account with appropriate permissions
2. **GCP Authentication**: 
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```
3. **Python Dependencies**:
   ```bash
   pip install pandas pyarrow yt-dlp absl-py requests google-cloud-storage tqdm
   ```

### GCP Quotas

- Default IP address quota per region: **69**
- Recommended max workers per zone: **68** (leaving 1 for the server)
- For 408 workers, use at least **6 zones**

### File Structure

```
starship/
├── prepare_laion_disco_input.py    # Convert parquet to JSON
├── download_laion_disco.sh         # Main download script
├── README_AUDIO.md                 # This file
├── src/starship/
│   ├── app_audio.py                # Audio-optimized orchestrator
│   ├── servers/
│   │   ├── server.py               # Task distribution server
│   │   └── server.sh               # Server startup script
│   └── workers/
│       ├── worker_audio_only.py    # Audio download worker
│       └── worker_audio_only.sh    # Worker startup script
└── starship_inputs/                # Generated JSON files (created automatically)
```

## Quick Start

### 1. Prepare Input Files

Convert LAION-DISCO-12M parquet files to starship JSON format:

```bash
python3 prepare_laion_disco_input.py \
    --input /ocean/projects/cis210027p/shared/corpora/laion_laion_disco_12m \
    --output-dir ./starship_inputs \
    --chunked \
    --chunk-size 10000
```

This creates multiple JSON files (chunks) for parallel processing.

### 2. Download Audio (Simple)

Use the automated download script:

```bash
./download_laion_disco.sh --workers 408
```

### 3. Download Audio (Advanced)

Or use the Python app directly for more control:

```bash
cd src/starship
python3 app_audio.py \
    --gcp_project=scs-lti-youtube-downloader \
    --num_workers=408 \
    --input=../../starship_inputs/laion_disco_chunk_000000.json \
    --zones=us-central1-a,us-central1-b,us-central1-c,us-east1-b,us-east1-c,us-east1-d \
    --max_workers_per_zone=68 \
    --bucket=scs-lti-laion-audio \
    --output_folder=laion_disco_12m \
    --save_original_audio=True
```

## Usage

### Option 1: Using the Shell Script (Recommended)

The shell script automates the entire process:

```bash
# Show help
./download_laion_disco.sh --help

# Prepare files only (dry run)
./download_laion_disco.sh --prepare-only

# Download with custom settings
./download_laion_disco.sh \
    --workers 200 \
    --chunk-size 5000 \
    --bucket my-bucket \
    --output my-output-folder

# Download specific chunk range
./download_laion_disco.sh \
    --start-chunk 0 \
    --end-chunk 10 \
    --workers 408

# Skip preparation and use existing files
./download_laion_disco.sh --skip-prepare --workers 408
```

### Option 2: Step-by-Step Manual Process

#### Step 1: Prepare Input Files

```bash
# For full dataset
python3 prepare_laion_disco_input.py \
    --input /ocean/projects/cis210027p/shared/corpora/laion_laion_disco_12m \
    --output laion_disco_all.json

# For chunked processing (recommended)
python3 prepare_laion_disco_input.py \
    --input /ocean/projects/cis210027p/shared/corpora/laion_laion_disco_12m \
    --output-dir ./starship_inputs \
    --chunked \
    --chunk-size 10000

# For specific range (testing)
python3 prepare_laion_disco_input.py \
    --input /ocean/projects/cis210027p/shared/corpora/laion_laion_disco_12m \
    --output test_subset.json \
    --start 0 \
    --end 100
```

#### Step 2: Launch Download

```bash
cd src/starship

# Basic usage
python3 app_audio.py \
    --gcp_project=YOUR_PROJECT \
    --input=../../starship_inputs/laion_disco_chunk_000000.json \
    --bucket=YOUR_BUCKET

# With all options
python3 app_audio.py \
    --gcp_project=scs-lti-youtube-downloader \
    --num_workers=408 \
    --input=../../starship_inputs/laion_disco_chunk_000000.json \
    --zones=us-central1-a,us-central1-b,us-central1-c,us-east1-b,us-east1-c,us-east1-d \
    --max_workers_per_zone=68 \
    --bucket=scs-lti-laion-audio \
    --output_folder=laion_disco_12m/chunk_000000 \
    --instance_type=n1-standard-1
```

## Advanced Options

### Input Preparation Options

```bash
--input DIR              # Input directory with parquet files
--output FILE            # Single output JSON file
--output-dir DIR         # Directory for chunked output files
--chunked                # Create multiple chunk files
--chunk-size N           # Records per chunk (default: 10000)
--start N                # Start index for subset processing
--end N                  # End index for subset processing
```

### Download Script Options

```bash
-h, --help              # Show help message
-p, --prepare-only      # Only prepare files, don't download
-s, --skip-prepare      # Skip preparation, use existing files
-c, --chunk-size SIZE   # Records per chunk (default: 10000)
-w, --workers NUM       # Number of workers (default: 408)
-b, --bucket NAME       # GCP bucket name
-o, --output FOLDER     # Output folder in bucket
--start-chunk N         # Start from chunk N
--end-chunk N           # End at chunk N
--project PROJECT       # GCP project ID
```

### App Audio Options

```bash
--gcp_project           # GCP project ID (required)
--input                 # Input JSON file (required)
--num_workers           # Number of workers (default: 1)
--bucket                # GCP bucket (default: g-starship-data)
--output_folder         # Output folder in bucket (default: audio)
--zones                 # Comma-separated zones (default: us-central1-a)
--max_workers_per_zone  # Max workers per zone (default: 72)
--instance_type         # GCP instance type (default: n1-standard-1)
--save_original_audio   # Save original format (default: True)
```

## Monitoring

### Real-Time Status

While the download is running, you can check status via the server endpoint:

```bash
# Get the server IP from the logs, then:
curl http://SERVER_IP/status
```

The status JSON includes:
- Total tasks
- Finished/failed/skipped/downloading counts
- Worker statuses
- Completion flag

### GCP Storage Browser

Monitor downloaded files in the GCP console:
```
https://console.cloud.google.com/storage/browser/YOUR_BUCKET/laion_disco_12m/
```

### Command Line

```bash
# List downloaded files
gsutil ls -lh gs://YOUR_BUCKET/laion_disco_12m/

# Count downloaded files
gsutil ls gs://YOUR_BUCKET/laion_disco_12m/**/*.webm | wc -l
gsutil ls gs://YOUR_BUCKET/laion_disco_12m/**/*.m4a | wc -l

# Check total size
gsutil du -sh gs://YOUR_BUCKET/laion_disco_12m/
```

## Output Structure

Each audio file is stored with metadata:

```
gs://bucket/laion_disco_12m/chunk_000000/AB/ABcdEfGh123/
├── ABcdEfGh123.webm              # Original audio file
├── ABcdEfGh123.info.json         # YouTube metadata (from yt-dlp)
├── ABcdEfGh123.description       # Video description
└── meta.json                     # Combined metadata
```

### meta.json Structure

```json
{
  "song_id": "ABcdEfGh123",
  "title": "Song Title",
  "artist_names": ["Artist Name"],
  "album_name": "Album Name",
  "duration": 213,
  "views": "945K plays",
  "isExplicit": true,
  "youtube_title": "Artist - Song Title (Official Video)",
  "youtube_duration": 213,
  "youtube_uploader": "Artist VEVO",
  "youtube_view_count": 12345678,
  "audio_format": "webm",
  "audio_codec": "opus",
  "audio_bitrate": 160,
  "sample_rate": 48000,
  "channels": 2,
  "download_timestamp": 1699234567.89
}
```

## Troubleshooting

### Issue: "Starship is already running in zone X"

**Solution**: Previous instances weren't cleaned up properly. Clean them manually:

```bash
gcloud compute instances list | grep starship
gcloud compute instances delete INSTANCE_NAME --zone=ZONE
```

### Issue: "Could not launch N workers"

**Solution**: You've exceeded the IP address quota. Either:
1. Reduce `--num_workers`
2. Add more zones to `--zones`
3. Request a quota increase from GCP

### Issue: Download fails with "HTTP Error 429: Too Many Requests"

**Solution**: YouTube rate limiting. The system automatically retries, but you can:
1. Reduce the number of workers
2. Add delays between chunks
3. Use the chunked processing approach

### Issue: "No audio file found after download"

**Solution**: The video might not have audio, or it's region-blocked. Check:
1. The error logs on the worker
2. Try downloading manually with yt-dlp
3. Check if the video is available in your region

### Issue: Workers not connecting to server

**Solution**: Check firewall rules:
```bash
gcloud compute firewall-rules list | grep starship
```

### Issue: Out of disk space on worker

**Solution**: Workers use f1-micro instances with limited disk. The system cleans up after each download, but if you have issues:
1. Check the worker logs
2. Use a larger instance type with `--instance_type=n1-standard-1`

## Performance Tips

1. **Optimal Worker Count**: 
   - Start with 100-200 workers for testing
   - Scale up to 400+ for production
   - Balance between speed and cost

2. **Chunk Size**:
   - Smaller chunks (5000): More flexibility, easier to resume
   - Larger chunks (20000): Less overhead, better for large datasets

3. **Zone Selection**:
   - Use zones close to your location for better monitoring
   - Spread across multiple zones for quota limits
   - Use zones with lower pricing if cost is a concern

4. **Cost Optimization**:
   - Use preemptible instances (requires code modification)
   - Clean up promptly when done
   - Use smaller instance types for workers (f1-micro is sufficient)

## Cost Estimation

Approximate costs for downloading LAION-DISCO-12M (~12M songs):

- **Compute**: 
  - Server: 1 x n1-standard-1 x ~50 hours = ~$2.50
  - Workers: 408 x f1-micro x ~50 hours = ~$350
  
- **Network**: 
  - Egress from YouTube: Free
  - Upload to GCP: Free
  
- **Storage**:
  - ~50TB audio data (estimated) = ~$1000/month

**Total**: ~$350 for compute + ongoing storage costs

## References

- [Starship Original Documentation](README.md)
- [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp)
- [LAION-DISCO Dataset](https://huggingface.co/datasets/laion/laion-disco-12m)
- [GCP Compute Engine Pricing](https://cloud.google.com/compute/pricing)

## Support

For issues or questions:
1. Check the logs in GCP Console
2. Review worker/server output
3. Check GCP quotas and limits
4. Verify GCP authentication and permissions

