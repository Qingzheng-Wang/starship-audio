import atexit
import json
import time
from functools import partial

import flask
from absl import app, flags
from apscheduler.schedulers.background import BackgroundScheduler
from flask import request

flags.DEFINE_integer("port", default=80, help="The port to run the server on.")
flags.DEFINE_string("input", default="videos.json", help="The file to read the videos from.")
flags.DEFINE_integer("timeout", default=60, help="The timeout for waiting on a worker.")
flags.DEFINE_integer("retries", default=3, help="The number of retries to allow for a video.")
FLAGS = flags.FLAGS


def _check_and_retry_downloads(metadata):
    for video_id, data in metadata.items():
        if data["status"] == "downloading" and time.time() - data["start_time"] > FLAGS.timeout:
            data["status"] = "waiting"
            data["retries"] += 1
            data["error"] = "Timeout waiting on worker"


def _get_next_video_route(flask_app, metadata, video_data, videos, workers_seen):

    @flask_app.route("/next_video", methods=["POST", "GET"])
    def next_video():  # noqa
        if request.method == "GET":
            # Get a new video to download
            worker_id = request.args["worker_id"]
            workers_seen[worker_id] = {
                "last_seen": time.time(),
                "status": request.args["worker_status"],
                "notified_finished": False,
                "message": request.args["worker_message"],
            }

            if request.args["worker_status"] != "ok":
                # Make sure that any videos that are downloading are redirected to the next worker
                for video_id in videos:
                    if metadata[video_id]["status"] == "downloading" and metadata[video_id]["worker_id"] == worker_id:
                        metadata[video_id]["status"] = "waiting"
                        metadata[video_id]["error"] = request.args["worker_message"]
                        metadata[video_id]["retries"] += 1

                # Tell the worker they should give up
                return flask.jsonify({"finished": True})

            if not any(v["status"] == "waiting" for v in metadata.values()):
                if any(v["status"] == "downloading" for v in metadata.values()):
                    return flask.jsonify({"pending_finish": True})
                return flask.jsonify({"finished": True})

            # Get the next video
            next_video_id = next(k for k, v in metadata.items() if v["status"] == "waiting")
            metadata[next_video_id]["status"] = "downloading"
            metadata[next_video_id]["error"] = None
            metadata[next_video_id]["start_time"] = time.time()
            metadata[next_video_id]["end_time"] = None

            output_data = {
                "_id": next_video_id,
                **video_data[next_video_id],
            }
            return flask.jsonify(output_data)

        elif request.method == "POST":
            # A video has been finished
            data = request.get_json()
            if data is None:
                return flask.jsonify({"error": "No data provided"})
            if "video_id" not in data:
                return flask.jsonify({"error": "No video_id provided"})
            if "status" not in data:
                return flask.jsonify({"error": "No status provided"})
            if "worker_id" not in data:
                return flask.jsonify({"error": "No worker_id provided"})

            video_id = data["video_id"]

            if data["status"] in ("ok", "skipped"):
                # The video has been downloaded
                metadata[video_id]["status"] = "finished" if data["status"] == "ok" else "skipped"
                metadata[video_id]["end_time"] = time.time()
                metadata[video_id]["error"] = None
            else:
                # The video download failed
                metadata[video_id]["end_time"] = time.time()
                metadata[video_id]["error"] = data.get("status", "Unknown error")
                if metadata[video_id]["retries"] < FLAGS.retries:
                    metadata[video_id]["status"] = "waiting"
                    metadata[video_id]["retries"] += 1
                else:
                    metadata[video_id]["status"] = "failed"

            # Update the last workers
            if data["worker_id"] in workers_seen:
                workers_seen[data["worker_id"]]["last_seen"] = time.time()
                if "worker_status" in data:
                    workers_seen[data["worker_id"]]["status"] = data["worker_status"]
                if "worker_message" in data:
                    workers_seen[data["worker_id"]]["message"] = data["worker_message"]

            return flask.jsonify({"status": "ok"})

    return next_video


def _get_status_route(flask_app, metadata, videos, workers_seen):

    @flask_app.route("/status")
    def status():
        return {
            "total": len(videos),
            "finished": len([1 for v in metadata.values() if v["status"] in ("finished", "skipped", "failed")]),
            "failed": len([1 for v in metadata.values() if v["status"] == "failed"]),
            "waiting": len([1 for v in metadata.values() if v["status"] == "waiting"]),
            "downloading": len([1 for v in metadata.values() if v["status"] == "downloading"]),
            "skipped": len([1 for v in metadata.values() if v["status"] == "skipped"]),
            "retrying": len([1 for v in metadata.values() if v["status"] == "waiting" and v["retries"] > 0]),
            "workers": workers_seen,
            "done": all(v["status"] not in ("waiting", "downloading") for v in metadata.values()),
        }

    return status


def main(*unused_argv):

    # Create the flask app
    flask_app = flask.Flask(__name__)

    # Load the underlying data for the videos that need to be downloaded
    with open(FLAGS.input) as video_files:
        inputs = json.load(video_files)

    # Setup the queue to hold the videos that need to be downloaded
    video_data = dict(enumerate(inputs))
    videos = set(video_data.keys())

    # Setup the metadata
    metadata = {
        k: {
            "status": "waiting",
            "error": None,
            "retries": 0,
            "start_time": None,
            "end_time": None,
            "worker_id": None,
        }
        for k in videos
    }

    # Setup some data for handling workers
    workers_seen = {}

    # Setup the routes
    _get_next_video_route(flask_app, metadata, video_data, videos, workers_seen)
    _get_status_route(flask_app, metadata, videos, workers_seen)

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=partial(_check_and_retry_downloads, metadata=metadata), trigger="interval", seconds=5)
    scheduler.start()

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    flask_app.run(host="0.0.0.0", port=FLAGS.port)


if __name__ == "__main__":
    app.run(main)
