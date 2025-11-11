"""
Audio-only worker for LAION-DISCO-12M dataset.
Downloads audio in original format, preserving bit depth, format, channels, etc.
"""

import json
import os
import shutil
import sys
import time
from typing import Any, Dict

import requests
from absl import app, flags, logging
from google.cloud import storage
from yt_dlp import YoutubeDL

flags.DEFINE_string("server_ip", None, "The IP of the server to connect to")
flags.DEFINE_string("bucket", None, "The GCP bucket to upload to")
flags.DEFINE_string("instance_name", None, "The instance name")
flags.DEFINE_string("folder", "audio", "The folder in the bucket to save audio to")
flags.DEFINE_bool("no_gcp", False, "Don't upload to GCP")
flags.DEFINE_bool("save_original", True, "Save original audio format without conversion")
flags.DEFINE_string("local_output", None, "Local output directory (if not using GCP)")

FLAGS = flags.FLAGS


def _download_audio_to_gcp(
    audio_data: Dict[str, Any], 
    storage_client: Any, 
    bucket: str, 
    output_folder: str
) -> None:
    """
    Download audio from YouTube and upload to GCP or save locally.
    Preserves original audio format (bit depth, codec, channels, sample rate).
    """
    
    # Create temporary directory for audio files
    if os.path.exists("./audiodata"):
        shutil.rmtree("./audiodata", ignore_errors=True)
    os.mkdir("./audiodata")

    song_id = audio_data["song_id"]
    remote_output_path = f'{output_folder}/{audio_data["output_path"]}'
    
    # Check if already exists in GCP
    if storage_client is not None and storage_client.get_bucket(bucket).blob(remote_output_path).exists():
        logging.info("Skipping %s - already exists in GCP", song_id)
        try:
            requests.post(
                f"http://{FLAGS.server_ip}/next_video",
                json={
                    "video_id": audio_data["_id"],
                    "status": "skipped",
                    "error": None,
                    "worker_id": FLAGS.instance_name,
                },
            )
        except Exception as e:
            logging.error(f"Failed to post status to server: {e}")
        return

    # Check if already exists locally
    if FLAGS.local_output and not FLAGS.no_gcp is False:
        local_path = os.path.join(FLAGS.local_output, audio_data["output_path"])
        if os.path.exists(local_path):
            logging.info("Skipping %s - already exists locally", song_id)
            try:
                requests.post(
                    f"http://{FLAGS.server_ip}/next_video",
                    json={
                        "video_id": audio_data["_id"],
                        "status": "skipped",
                        "error": None,
                        "worker_id": FLAGS.instance_name,
                    },
                )
            except Exception as e:
                logging.error(f"Failed to post status to server: {e}")
            return

    # yt-dlp options for audio-only download with original format preservation
    ydl_opts = {
        # Download best audio format (usually opus in webm, m4a/aac, etc.)
        "format": "bestaudio/best",
        
        # Output template
        'outtmpl': './audiodata/%(id)s.%(ext)s',
        
        # Don't extract video
        "extract_audio": False,  # Don't force audio extraction (keep original container)
        
        # Metadata options
        "writeinfojson": True,  # Save metadata
        "writethumbnail": False,  # Don't need thumbnails for audio
        "writedescription": True,
        
        # Network options
        "geo_bypass": True,
        "quiet": True,
        "no_warnings": False,
        
        # Error handling
        "ignoreerrors": False,
        "no_color": True,
        
        # Don't do any post-processing (preserve original format)
        "postprocessors": [],  # No post-processing to keep original format
        
        # Anti-bot detection
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
        'sleep_interval': 2,
        'max_sleep_interval': 5,
        
        # Retry settings
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
    }

    logging.info("Downloading audio: %s (song_id: %s)", audio_data["_id"], song_id)
    logging.info("URL: %s", audio_data.get("url", f"https://www.youtube.com/watch?v={song_id}"))

    # Override download options if specified
    if "ytdl_opts" in audio_data:
        ydl_opts.update(audio_data["ytdl_opts"])

    error_message = "Could not download audio for an unknown reason"
    try:
        with YoutubeDL(ydl_opts) as downloader:
            # Extract info and download
            url = audio_data.get("url", f"https://www.youtube.com/watch?v={song_id}")
            res = downloader.extract_info(url, download=True)
    except Exception as e:
        logging.error(f"Failed to extract audio info: {e}")
        error_message = str(e)
        res = None

    if res is None:
        logging.error("Failed to download %s", song_id)
        try:
            requests.post(
                f"http://{FLAGS.server_ip}/next_video",
                json={
                    "video_id": audio_data["_id"],
                    "status": "failed",
                    "error": "Could not download audio",
                    "worker_id": FLAGS.instance_name,
                    "worker_message": error_message,
                },
            )
        except Exception as e:
            logging.error(f"Failed to post status to server: {e}")
        
        # Clean up
        shutil.rmtree("./audiodata", ignore_errors=True)
        return

    # Write enhanced metadata including audio format information
    metadata = {
        "song_id": song_id,
        # Original dataset metadata
        "title": audio_data.get("title"),
        "artist_names": audio_data.get("artist_names"),
        "album_name": audio_data.get("album_name"),
        "duration": audio_data.get("duration"),
        "views": audio_data.get("views"),
        "isExplicit": audio_data.get("isExplicit"),
        # YouTube metadata
        "youtube_title": res.get("title"),
        "youtube_duration": res.get("duration"),
        "youtube_uploader": res.get("uploader"),
        "youtube_view_count": res.get("view_count"),
        # Audio format info (original format preserved)
        "audio_format": res.get("ext"),  # File extension (webm, m4a, opus, etc.)
        "audio_codec": res.get("acodec"),  # Audio codec (opus, aac, mp3, etc.)
        "audio_bitrate": res.get("abr"),  # Bitrate in kbps
        "sample_rate": res.get("asr"),  # Sample rate in Hz
        "channels": res.get("audio_channels"),  # Number of channels
        # Download info
        "download_timestamp": time.time(),
    }
    
    with open("./audiodata/meta.json", "w", encoding='utf-8') as jf:
        json.dump(metadata, jf, ensure_ascii=False, indent=2)

    # Find the downloaded audio file
    audio_files = [f for f in os.listdir("./audiodata") if not f.endswith('.json') and not f.endswith('.txt')]
    
    if not audio_files:
        logging.error("No audio file found after download for %s", song_id)
        try:
            requests.post(
                f"http://{FLAGS.server_ip}/next_video",
                json={
                    "video_id": audio_data["_id"],
                    "status": "failed",
                    "error": "No audio file found after download",
                    "worker_id": FLAGS.instance_name,
                },
            )
        except Exception as e:
            logging.error(f"Failed to post status to server: {e}")
        
        shutil.rmtree("./audiodata", ignore_errors=True)
        return

    audio_filename = audio_files[0]
    logging.info(f"Downloaded audio file: {audio_filename}")
    logging.info(f"Audio format: {metadata.get('audio_format')}, "
                f"Codec: {metadata.get('audio_codec')}, "
                f"Sample rate: {metadata.get('sample_rate')} Hz, "
                f"Channels: {metadata.get('channels')}, "
                f"Bitrate: {metadata.get('audio_bitrate')} kbps")

    # Upload to GCP or save locally
    if storage_client is not None:
        # Upload all files to GCP
        for file in os.listdir("./audiodata"):
            file_path = f"./audiodata/{file}"
            gcp_path = f"{remote_output_path}/{file}"
            logging.info(f"Uploading {file} to GCP at {gcp_path}")
            storage_client.get_bucket(bucket).blob(gcp_path).upload_from_filename(file_path)
    elif FLAGS.local_output:
        # Save to local directory
        local_dir = os.path.join(FLAGS.local_output, audio_data["output_path"])
        os.makedirs(local_dir, exist_ok=True)
        for file in os.listdir("./audiodata"):
            src = f"./audiodata/{file}"
            dst = os.path.join(local_dir, file)
            logging.info(f"Saving {file} to {dst}")
            shutil.copy2(src, dst)
    else:
        logging.warning("Neither GCP nor local output specified, files in ./audiodata/")

    # Clean up temporary files
    shutil.rmtree("./audiodata", ignore_errors=True)

    # Report success to server
    try:
        requests.post(
            f"http://{FLAGS.server_ip}/next_video",
            json={
                "video_id": audio_data["_id"],
                "status": "ok",
                "error": None,
                "worker_id": FLAGS.instance_name,
            },
        )
    except Exception as e:
        logging.error(f"Failed to post success status to server: {e}")


def main(*unused_argv):
    worker_id = FLAGS.instance_name

    if FLAGS.no_gcp:
        logging.info("Not uploading to GCP")
        storage_client = None
    else:
        storage_client = storage.Client()
    
    worker_status = "ok"
    worker_message = ""

    logging.info(f"Starting audio-only worker: {worker_id}")
    logging.info(f"Save original format: {FLAGS.save_original}")
    logging.info(f"Local output: {FLAGS.local_output if FLAGS.local_output else 'None (using GCP)'}")

    while True:
        try:
            # Request next audio download task
            next_audio_data = requests.get(
                f"http://{FLAGS.server_ip}/next_video?worker_id={worker_id}&worker_status={worker_status}&worker_message={worker_message}"
            )
            
            try:
                next_audio_data = next_audio_data.json()
            except json.decoder.JSONDecodeError:
                logging.error(f"Failed to decode JSON from server: {next_audio_data.text}")
                sys.exit(1)

            # Check if work is done
            if "pending_finish" in next_audio_data and next_audio_data["pending_finish"]:
                logging.info(f"Worker {worker_id} is pending_finish")
                time.sleep(5)
                continue

            if "finished" in next_audio_data and next_audio_data["finished"]:
                logging.info(f"Worker {worker_id} is finished")
                break

            # Download audio
            try:
                _download_audio_to_gcp(
                    next_audio_data, 
                    storage_client, 
                    FLAGS.bucket, 
                    FLAGS.folder
                )
                worker_status = "ok"
                worker_message = ""
            except Exception as e:
                logging.error(f"Failed to download audio: {e}")
                worker_status = "error"
                worker_message = str(e)
                continue

        except requests.exceptions.ConnectionError:
            logging.error("Failed to connect to server")
            time.sleep(5)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            worker_status = "error"
            worker_message = str(e)

    logging.info(f"Worker {worker_id} shutting down")


if __name__ == "__main__":
    app.run(main)




