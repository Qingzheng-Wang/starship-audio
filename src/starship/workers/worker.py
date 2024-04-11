import json
import os
import shutil
import subprocess
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
flags.DEFINE_string("folder", "videos", "The folder in the bucket to save videos to")
flags.DEFINE_bool("no_gcp", False, "Don't upload to GCP")

FLAGS = flags.FLAGS


def _download_video_to_gcp(video_data: Dict[str, Any], storage_client: Any, bucket: str, output_folder: str) -> None:

    if os.path.exists("./videodata"):
        shutil.rmtree("./videodata", ignore_errors=True)
    os.mkdir("./videodata")

    remote_output_path = f'{output_folder}/{video_data["output_path"]}'
    # If the blob exists, then we don't need to download it again
    if storage_client is not None and storage_client.get_bucket(bucket).blob(remote_output_path).exists():
        logging.info("Skipping %s", video_data["_id"])
        try:
            requests.post(
                f"http://{FLAGS.server_ip}/next_video",
                json={
                    "video_id": video_data["_id"],
                    "status": "skipped",
                    "error": None,
                    "worker_id": FLAGS.instance_name,
                },
            )
        except Exception as e:
            logging.error(f"Failed to post video to server: {e}")

        return

    # Default download options
    ydl_opts = {
        "format": "best",
        "allsubtitles": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "writedescription": True,
        "writeinfojson": True,
        "writeannotations": True,
        "writethumbnail": True,
        "geo_bypass": True,
        "outtmpl": "./videodata/%(title)s.%(ext)s",
        "quiet": True,
    }

    logging.info("Downloading %s", video_data["_id"])
    logging.info(video_data)

    # Override the download options if it's requested
    if "ytdl_opts" in video_data:
        ydl_opts.update(video_data["ytdl_opts"])

    error_message = "Could not download video for an unknown reason"
    try:
        with YoutubeDL(ydl_opts) as downloader:
            res = downloader.extract_info(str(video_data["url"]), download=True)
    except Exception as e:
        logging.error(f"Failed to extract video info: {e}")
        error_message = str(e)
        res = None

    if res is None:
        logging.error("Failed to download %s", video_data["_id"])
        try:
            requests.post(
                f"http://{FLAGS.server_ip}/next_video",
                json={
                    "video_id": video_data["_id"],
                    "status": "skipped",
                    "error": "Could not download video",
                    "worker_id": FLAGS.instance_name,
                    "worker_message": error_message,
                },
            )
        except Exception as e:
            logging.error(f"Failed to post video to server: {e}")

        return

    # Write the metadata
    with open("./videodata/meta.json", "w") as jf:
        json.dump(res, jf)

    # Do any processing required
    if "postprocessing_input" not in video_data:
        video_filename = [f"./videodata/{f}" for f in os.listdir("./videodata") if f.endswith(res["ext"])][
            0
        ]  # HUGE HACK
    else:
        video_filename = video_data["postprocessing_input"]

    if "postprocessing" in video_data:
        subprocess.call(f'ffmpeg -i {video_filename} {video_data["postprocessing"]}', shell=True)
        if "postprocessing_output" in video_data:
            os.remove(video_filename)
            video_filename = video_data["postprocessing_output"]
            # Move the file to the correct location
            os.rename(video_filename, f"./videodata/{video_filename}")

    # Upload all files to GCP
    for file in os.listdir("./videodata"):
        if storage_client is not None:
            storage_client.get_bucket(bucket).blob(f"{remote_output_path}/{file}").upload_from_filename(
                f"./videodata/{file}"
            )
        else:
            print(f"Uploading ./videodata/{file} to GCP at {remote_output_path}/{file}")

    # Delete the temporary files
    shutil.rmtree("./videodata", ignore_errors=True)

    try:
        requests.post(
            f"http://{FLAGS.server_ip}/next_video",
            json={
                "video_id": video_data["_id"],
                "status": "ok",
                "error": None,
                "worker_id": FLAGS.instance_name,
            },
        )
    except Exception as e:
        logging.error(f"Failed to post video to server: {e}")


def main(*unused_argv):
    worker_id = FLAGS.instance_name

    if FLAGS.no_gcp:
        logging.info("Not uploading to GCP")
        storage_client = None
    else:
        storage_client = storage.Client()
    worker_status = "ok"
    worker_message = ""

    while True:
        try:
            next_video_data = requests.get(
                f"http://{FLAGS.server_ip}/next_video?worker_id={worker_id}&worker_status={worker_status}&worker_message={worker_message}"
            )
            try:
                next_video_data = next_video_data.json()
            except json.decoder.JSONDecodeError:
                logging.error(f"Failed to decode JSON from server: {next_video_data.text}")
                sys.exit(1)

            if "pending_finish" in next_video_data and next_video_data["pending_finish"]:
                logging.info(f"Worker {worker_id} is pending_finish")
                time.sleep(5)
                continue

            if "finished" in next_video_data and next_video_data["finished"]:
                logging.info(f"Worker {worker_id} is finished")
                break

            try:
                _download_video_to_gcp(next_video_data, storage_client, FLAGS.bucket, FLAGS.folder)
            except Exception as e:
                logging.error(f"Failed to download video: {e}")
                worker_status = "error"
                worker_message = str(e)
                continue

        except requests.exceptions.ConnectionError:
            logging.error("Failed to connect to server")
            time.sleep(5)
        except Exception:
            worker_status = "error"


if __name__ == "__main__":
    app.run(main)
