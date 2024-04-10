"""
Main app for starship - a client designed to fetch YouTube videos at scale.
"""

import atexit
import json
import os
import sys
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Tuple

import requests
from absl import app, flags, logging
from google.cloud import storage
from googleapiclient import discovery

from starship.gcp.utils.compute import create_instance, get_instance_ip, wait_for_operation
from starship.gcp.utils.storage import upload_file_to_gcp
from starship.utils import local_relpath, random_string

flags.DEFINE_string("input", None, help="Input list of video IDs to download, one video per line.")
flags.DEFINE_integer("num_workers", 1, help="The number of workers to create.")
flags.DEFINE_string("gcp_project", None, help="The GCP project to use")
flags.DEFINE_string("bucket", "g-starship-data", help="The GCP bucket to use")
flags.DEFINE_string("output_folder", "videos", help="The output folder to use within the GCP bucket for the vidoes.")
flags.DEFINE_list("zones", ["us-central1-a"], help="The zones to launch workers in.")
flags.DEFINE_integer("max_workers_per_zone", 72, help="The maximum number of workers per zone.")
flags.DEFINE_string("instance_type", default="n1-standard-1", help="The instance type to use.")
flags.DEFINE_string("input_data_type", default="json", help="The type of input data to use.")

flags.mark_flags_as_required(["gcp_project", "input"])

FLAGS = flags.FLAGS


def get_exit_handler(compute, create_ops: Dict[str, List[Any]], run_name: str) -> Callable[[], None]:
    def exit_handler():
        # Wait on all of the create_ops to finish running
        for zone, ops in create_ops.items():
            for op in ops:
                try:
                    wait_for_operation(compute, FLAGS.gcp_project, zone, op["name"])
                except Exception as ex:
                    logging.error(ex)

        # Search all of the zones for starship instances, and remove them.
        ops = []
        for zone in FLAGS.zones:
            running_instances = compute.instances().list(project=FLAGS.gcp_project, zone=zone).execute()
            if "items" in running_instances:
                for instance in running_instances["items"]:
                    if f"starship-{run_name}" in instance["name"]:
                        ops.append(
                            (
                                instance["name"],
                                zone,
                                compute.instances()
                                .delete(project=FLAGS.gcp_project, zone=zone, instance=instance["name"])
                                .execute(),
                            )
                        )
        for name, zone, op in ops:
            logging.info("Waiting for %s to be removed...", name)
            wait_for_operation(compute, FLAGS.gcp_project, zone, op["name"])

    return exit_handler


def _discover_running_instances(compute: Any, project: str, zones: List[str]) -> None:
    for zone in zones:
        running_instances = compute.instances().list(project=project, zone=zone).execute()
        if "items" in running_instances:
            for instance in running_instances["items"]:
                if "starship" in instance["name"]:
                    logging.error(
                        "Starship is already running in zone %s. Make sure it is done running, and try again.", zone
                    )
                    sys.exit(1)
            logging.info("Zone %s has no running starship instances. Continuing...", zone)
        else:
            logging.info("Zone %s has no running instances. Continuing...", zone)


def _load_data_from_file(filepath: str, data_type: str) -> List[Dict[str, Any]]:
    with open(filepath) as f:
        if data_type == "file_list":
            return [
                {
                    "url": line.strip(),
                }
                for line in f.readlines()
            ]
        elif data_type == "json":
            return json.load(f)
        raise ValueError(f"Unknown input data type: {data_type}")


def _upload_code_to_gcp(storage_client: Any, bucket: str, video_data: List[Dict[str, Any]]) -> None:
    # Upload the scripts and video data to the GCP bucket
    upload_file_to_gcp(storage_client, bucket, "server.py", local_relpath(__file__, "servers/server.py"))
    upload_file_to_gcp(storage_client, bucket, "worker.py", local_relpath(__file__, "workers/worker.py"))
    storage_client.get_bucket(bucket).blob("videos.json").upload_from_string(json.dumps(video_data))


def _start_server(compute: Any, project: str, zone: str, run_name: str) -> Tuple[Any, Tuple[str, str]]:
    server_name = f"starship-{run_name}-srv"
    server_op = create_instance(
        compute,
        project,
        zone,
        server_name,
        bucket=FLAGS.bucket,
        startup_script_file=local_relpath(__file__, "servers/server.sh"),
        machine_type=FLAGS.instance_type,
    )
    logging.info("Waiting for server to be created...")
    wait_for_operation(compute, project, zone, server_op["name"])
    internal_server_ip, external_server_ip = get_instance_ip(compute, project, zone, server_name)
    logging.info("Server created at %s.", external_server_ip)
    return server_op, (internal_server_ip, external_server_ip)


def _start_worker(
    compute: Any,
    project: str,
    zone: str,
    bucket: str,
    output_folder: str,
    run_name: str,
    worker_index: int,
    internal_server_ip: str,
) -> Any:
    try:
        worker_name = f"starship-{run_name}-wrk-{worker_index}"
        logging.info("Creating worker %s in zone %s", worker_name, zone)
        return create_instance(
            compute,
            project,
            zone,
            worker_name,
            bucket=bucket,
            startup_script_file=local_relpath(__file__, "workers/worker.sh"),
            machine_type="f1-micro",
            metadata={
                "items": [
                    {"key": "serverip", "value": internal_server_ip},
                    {"key": "folder", "value": output_folder},
                ]
            },
        )

    except Exception as ex:
        logging.error("Error launching worker: %s", str(ex))


def _poll_server_status(external_server_ip: str) -> bool:
    try:
        # Get the status from the server
        status = requests.get(f"http://{external_server_ip}/status", timeout=1)
        if status.status_code == 200:
            stat = status.json()
            logging.info(
                f'Finished {stat["finished"]}/{stat["total"]} ({stat["failed"]} failed, {stat["skipped"]} skipped, {stat["downloading"]} downloading)'
            )
            for k, v in stat["workers"].items():
                if v["status"] != "ok":
                    logging.error(f"Worker {k} failed: {v['status']}")
            if stat["done"]:
                logging.info("Finished processing!")
                return False
        else:
            logging.error("Server returned status code %s", status.status_code)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        logging.info("The server is not yet live... Retrying in 5s")
    except Exception as ex:
        logging.error("Error polling server: %s", str(ex))
    return True


def _cleanup_instances(compute: Any, project: str, zones: str, run_name: str) -> None:
    logging.info("Cleaning up instances... Please wait, this may take some time.")
    ops = []
    for zone in zones:
        running_instances = compute.instances().list(project=project, zone=zone).execute()
        if "items" in running_instances:
            ops.extend(
                (
                    instance["name"],
                    zone,
                    compute.instances().delete(project=project, zone=zone, instance=instance["name"]).execute(),
                )
                for instance in running_instances["items"]
                if f"starship-{run_name}" in instance["name"]
            )

    # This cleans up the server as well, since it has 'starship-run_name' in it's name.
    for name, zone, op in ops:
        logging.info("Waiting for %s to be removed...", name)
        wait_for_operation(compute, project, zone, op["name"])


def main(*unused_argv) -> None:
    # Set the environment variable for the google application credentials
    os.environ["GCLOUD_PROJECT"] = FLAGS.gcp_project

    # Construct the google API client for compute and storage
    compute = discovery.build("compute", "v1", cache_discovery=False)
    storage_client = storage.Client()

    # Print the instances already running
    _discover_running_instances(compute, FLAGS.gcp_project, FLAGS.zones)

    # Construct the instances
    current_zone = 0
    worker_ops = defaultdict(list)
    run_name = random_string(3)

    # Install the atexit hook, in case the app dies, we want to be sure to clean up all of the instances
    exit_handler = get_exit_handler(compute, worker_ops, run_name)
    atexit.register(exit_handler)

    # Build the video data
    video_data = _load_data_from_file(FLAGS.input, FLAGS.input_data_type)

    # Upload data to GCP bucket so the leader can use it
    _upload_code_to_gcp(storage_client, FLAGS.bucket, video_data)

    # Startup the server
    server_op, (internal_server_ip, external_server_ip) = _start_server(
        compute, FLAGS.gcp_project, FLAGS.zones[current_zone], run_name
    )
    worker_ops[FLAGS.zones[current_zone]].append(server_op)

    # Construct the workers
    for idx in range(FLAGS.num_workers):
        # Determine the zone for the worker
        if len(worker_ops[FLAGS.zones[current_zone]]) > FLAGS.max_workers_per_zone:
            current_zone += 1
        if current_zone >= len(FLAGS.zones):
            logging.warning(
                "Could not launch %i workers in only the following zones: %s. Increase the number of workers per zone, or add more zones.",
                FLAGS.num_workers,
                str(FLAGS.zones),
            )
            break
        worker_ops[FLAGS.zones[current_zone]].append(
            _start_worker(
                compute,
                FLAGS.gcp_project,
                FLAGS.zones[current_zone],
                FLAGS.bucket,
                FLAGS.output_folder,
                run_name,
                idx,
                internal_server_ip,
            )
        )

    logging.info(
        """
        Instances created.
        It will take some time for the instances to complete work.
        Check this URL: http://storage.googleapis.com/{}/videos/ for status.
        """.format(
            FLAGS.bucket
        )
    )

    while _poll_server_status(external_server_ip):
        time.sleep(5)

    _cleanup_instances(compute, FLAGS.gcp_project, FLAGS.zones, run_name)

    # Unregister the exit hook
    atexit.unregister(exit_handler)

    logging.info("Finished.")


def cli():
    app.run(main)


if __name__ == "__main__":
    app.run(main)
