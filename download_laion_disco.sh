#!/bin/bash

###############################################################################
# LAION-DISCO-12M Audio Download Script
# This script downloads audio from the LAION-DISCO-12M dataset using starship
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default configuration
LAION_DISCO_DIR="/ocean/projects/cis210027p/shared/corpora/laion_laion_disco_12m"
PROJECT_DIR="/ocean/projects/cis210027p/qwang20/rich_caption_data/starship"
STARSHIP_INPUT_DIR="${PROJECT_DIR}/starship_inputs_medium"
GCP_PROJECT="scs-lti-youtube-downloader"
GCP_BUCKET="scs-lti-laion-audio"
OUTPUT_FOLDER="laion_disco_12m"
NUM_WORKERS=408
CHUNK_SIZE=10000

# GCP zones (up to 68 workers per zone due to IP address quota)
ZONES="us-central1-a,us-central1-b,us-central1-c,us-east1-b,us-east1-c,us-east1-d,us-west1-a,us-west1-b,us-west1-c"
MAX_WORKERS_PER_ZONE=68

# Flags
PREPARE_ONLY=false
SKIP_PREPARE=true
START_CHUNK=0
END_CHUNK=-1  # -1 means all chunks

###############################################################################
# Functions
###############################################################################

source ~/miniconda3/etc/profile.d/conda.sh
conda activate espnet_fix

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Download audio from LAION-DISCO-12M dataset using starship.

OPTIONS:
    -h, --help              Show this help message
    -p, --prepare-only      Only prepare input files, don't start download
    -s, --skip-prepare      Skip preparation step (use existing input files)
    -c, --chunk-size SIZE   Number of records per chunk (default: ${CHUNK_SIZE})
    -w, --workers NUM       Number of workers (default: ${NUM_WORKERS})
    -b, --bucket NAME       GCP bucket name (default: ${GCP_BUCKET})
    -o, --output FOLDER     Output folder in bucket (default: ${OUTPUT_FOLDER})
    --start-chunk N         Start from chunk N (default: 0)
    --end-chunk N           End at chunk N (default: all)
    --project PROJECT       GCP project ID (default: ${GCP_PROJECT})

EXAMPLES:
    # Prepare input files only
    $0 --prepare-only

    # Download with 200 workers
    $0 --workers 200

    # Download specific chunk range
    $0 --start-chunk 0 --end-chunk 10

    # Use existing input files and start download
    $0 --skip-prepare --workers 408

EOF
}

###############################################################################
# Parse arguments
###############################################################################

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            print_usage
            exit 0
            ;;
        -p|--prepare-only)
            PREPARE_ONLY=true
            shift
            ;;
        -s|--skip-prepare)
            SKIP_PREPARE=true
            shift
            ;;
        -c|--chunk-size)
            CHUNK_SIZE="$2"
            shift 2
            ;;
        -w|--workers)
            NUM_WORKERS="$2"
            shift 2
            ;;
        -b|--bucket)
            GCP_BUCKET="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FOLDER="$2"
            shift 2
            ;;
        --start-chunk)
            START_CHUNK="$2"
            shift 2
            ;;
        --end-chunk)
            END_CHUNK="$2"
            shift 2
            ;;
        --project)
            GCP_PROJECT="$2"
            shift 2
            ;;
        *)
            print_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

###############################################################################
# Main script
###############################################################################

print_info "LAION-DISCO-12M Audio Download Script"
print_info "======================================"
print_info "LAION-DISCO directory: ${LAION_DISCO_DIR}"
print_info "Project directory: ${PROJECT_DIR}"
print_info "GCP Project: ${GCP_PROJECT}"
print_info "GCP Bucket: ${GCP_BUCKET}"
print_info "Output folder: ${OUTPUT_FOLDER}"
print_info "Number of workers: ${NUM_WORKERS}"
print_info "Chunk size: ${CHUNK_SIZE}"
print_info ""

# Check if LAION-DISCO directory exists
if [ ! -d "${LAION_DISCO_DIR}" ]; then
    print_error "LAION-DISCO directory not found: ${LAION_DISCO_DIR}"
    exit 1
fi

# Change to project directory
cd "${PROJECT_DIR}"

###############################################################################
# Step 1: Prepare input files
###############################################################################

if [ "${SKIP_PREPARE}" = false ]; then
    print_info "Step 1: Preparing input files from LAION-DISCO metadata..."
    
    # Create output directory
    mkdir -p "${STARSHIP_INPUT_DIR}"
    
    # Run the preparation script
    python3 prepare_laion_disco_input.py \
        --input "${LAION_DISCO_DIR}" \
        --output-dir "${STARSHIP_INPUT_DIR}" \
        --chunked \
        --chunk-size "${CHUNK_SIZE}"
    
    if [ $? -ne 0 ]; then
        print_error "Failed to prepare input files"
        exit 1
    fi
    
    print_info "Input files prepared successfully!"
    print_info "Created chunked JSON files in: ${STARSHIP_INPUT_DIR}"
    
    # Count the number of chunks created
    NUM_CHUNKS=$(ls -1 "${STARSHIP_INPUT_DIR}"/laion_disco_medium_*.json 2>/dev/null | wc -l)
    print_info "Number of chunks created: ${NUM_CHUNKS}"
else
    print_info "Skipping preparation step (using existing input files)"
    NUM_CHUNKS=$(ls -1 "${STARSHIP_INPUT_DIR}"/laion_disco_medium_*.json 2>/dev/null | wc -l)
    print_info "Number of existing chunks: ${NUM_CHUNKS}"
fi

if [ "${PREPARE_ONLY}" = true ]; then
    print_info "Preparation complete. Exiting (--prepare-only flag set)."
    exit 0
fi

###############################################################################
# Step 2: Start starship download
###############################################################################

print_info ""
print_info "Step 2: Starting starship audio download..."

# Determine chunk range
if [ "${END_CHUNK}" -eq -1 ]; then
    END_CHUNK=$((NUM_CHUNKS - 1))
fi

print_info "Processing chunks ${START_CHUNK} to ${END_CHUNK}"

# Set PYTHONPATH to include src directory
export PYTHONPATH="${PROJECT_DIR}/src:${PYTHONPATH}"

# Navigate to starship source directory
cd "${PROJECT_DIR}/src/starship" || {
    print_error "Failed to change to starship directory"
    exit 1
}

# Process each chunk
for chunk_idx in $(seq ${START_CHUNK} ${END_CHUNK}); do
    CHUNK_FILE="${STARSHIP_INPUT_DIR}/laion_disco_medium_$(printf '%04d' ${chunk_idx}).json"
    
    if [ ! -f "${CHUNK_FILE}" ]; then
        print_warn "Chunk file not found: ${CHUNK_FILE}, skipping..."
        continue
    fi
    
    print_info ""
    print_info "Processing chunk ${chunk_idx}/${END_CHUNK}: ${CHUNK_FILE}"
    print_info "----------------------------------------"
    
    # Run starship for this chunk
    python3 app_audio.py \
        --gcp_project="${GCP_PROJECT}" \
        --num_workers="${NUM_WORKERS}" \
        --input="${CHUNK_FILE}" \
        --zones="${ZONES}" \
        --max_workers_per_zone="${MAX_WORKERS_PER_ZONE}" \
        --bucket="${GCP_BUCKET}" \
        --output_folder="${OUTPUT_FOLDER}/chunk_$(printf '%04d' ${chunk_idx})" \
        --save_original_audio=True
    
    if [ $? -ne 0 ]; then
        print_error "Failed to download chunk ${chunk_idx}"
        print_warn "Continuing with next chunk..."
    else
        print_info "Successfully completed chunk ${chunk_idx}"
    fi
    
    # Add a delay between chunks to avoid rate limiting
    if [ ${chunk_idx} -lt ${END_CHUNK} ]; then
        print_info "Waiting 30 seconds before starting next chunk..."
        sleep 30
    fi
done

###############################################################################
# Done
###############################################################################

print_info ""
print_info "======================================"
print_info "Download process completed!"
print_info "======================================"
print_info "Output location: gs://${GCP_BUCKET}/${OUTPUT_FOLDER}/"
print_info ""
print_info "To check the downloaded files, run:"
print_info "  gsutil ls -lh gs://${GCP_BUCKET}/${OUTPUT_FOLDER}/"
print_info ""
print_info "To download the files locally, run:"
print_info "  gsutil -m cp -r gs://${GCP_BUCKET}/${OUTPUT_FOLDER}/ /your/local/path/"
print_info ""

