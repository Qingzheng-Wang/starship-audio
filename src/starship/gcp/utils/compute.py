import time
import os

from absl import logging


def wait_for_operation(compute, project, zone, operation):
    while True:
        result = compute.zoneOperations().get(project=project, zone=zone, operation=operation).execute()

        if result["status"] == "DONE":
            if "error" in result:
                raise Exception(result["error"])
            return result
        time.sleep(1)


def create_instance(
    compute, project, zone, name, bucket, startup_script_file, metadata=None, machine_type="n1-standard-1"
):
    # NOTE: Variables in the metadata will take precidence over bucket/startup_script_file in this function call.

    # Create a debian-9 image
    image_response = compute.images().getFromFamily(project="ubuntu-os-cloud", family="ubuntu-2204-lts").execute()
    source_disk_image = image_response["selfLink"]

    # Configure the machine
    machine_type_internal = f"zones/{zone}/machineTypes/{machine_type}"
    with open(startup_script_file) as startup_file:
        startup_script = startup_file.read()

    if metadata is None:
        metadata = {"items": []}
    if "items" not in metadata:
        metadata["items"] = []

    # Check to see if the metadata is missing items, and if it is, update those items.
    if not any(map(lambda x: x["key"] == "startup-script", metadata["items"])):
        metadata["items"].append({"key": "startup-script", "value": startup_script})
    if not any(map(lambda x: x["key"] == "bucket", metadata["items"])):
        metadata["items"].append({"key": "bucket", "value": bucket})
    if not any(map(lambda x: x["key"] == "iname", metadata["items"])):
        metadata["items"].append({"key": "iname", "value": name})

    logging.debug("Creating instance with metadata: %s", str(metadata))

    config = {
        "name": name,
        "machineType": machine_type_internal,
        # Specify the boot disk and the image to use as a source.
        "disks": [
            {
                "boot": True,
                "autoDelete": True,
                "initializeParams": {
                    "sourceImage": source_disk_image,
                },
            }
        ],
        # Specify a network interface with NAT to access the public
        # internet.
        "networkInterfaces": [
            {
                "network": os.getenv("STARSHIP_GCP_NETWORK", "global/networks/default"),
                "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
            }
        ],
        # Allow the instance to access cloud storage and logging.
        "serviceAccounts": [
            {
                "email": os.getenv("STARSHIP_GCP_SERVICE_ACCOUNT", "default"),
                "scopes": [
                    "https://www.googleapis.com/auth/devstorage.read_write",
                    "https://www.googleapis.com/auth/logging.write",
                ],
            }
        ],
        # Metadata is readable from the instance and allows you to
        # pass configuration from deployment scripts to instances.
        "metadata": metadata,
    }

    logging.debug("Creating instance with config: %s", str(config))
    operation = compute.instances().insert(project=project, zone=zone, body=config).execute()
    logging.info("Instance created: %s", str(operation))

    return operation


def get_instance_ip(compute, project: str, zone: str, instance_name: str) -> str:
    logging.info("Fetching IP for instance: %s in zone %s", instance_name, zone)
    response = compute.instances().get(project=project, zone=zone, instance=instance_name).execute()
    internal_instance_ip = str(response["networkInterfaces"][0]["networkIP"])
    external_instance_ip = str(response["networkInterfaces"][0]["accessConfigs"][0]["natIP"])
    logging.info(
        "The IP of %s is %s (internal) and %s (external)", instance_name, internal_instance_ip, external_instance_ip
    )
    return internal_instance_ip, external_instance_ip


def get_instance_external_ip(compute, project: str, zone: str, instance_name: str) -> str:
    logging.info("Fetching external IP for instance: %s in zone %s", instance_name, zone)
    response = compute.instances().get(project=project, zone=zone, instance=instance_name).execute()
    instance_ip = str(response["networkInterfaces"][0]["accessConfigs"][0]["natIP"])
    logging.info("The external IP of %s is %s", instance_name, instance_ip)
    return instance_ip


def get_instance_internal_ip(compute, project: str, zone: str, instance_name: str) -> str:
    logging.info("Fetching internal IP for instance: %s in zone %s", instance_name, zone)
    response = compute.instances().get(project=project, zone=zone, instance=instance_name).execute()
    instance_ip = str(response["networkInterfaces"][0]["networkIP"])
    logging.info("The internal IP of %s is %s", instance_name, instance_ip)
    return instance_ip
