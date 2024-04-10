"""
Google cloud storage utilities.
"""

import google.cloud.storage.client


def upload_file_to_gcp(
    storage_client: google.cloud.storage.client.Client, bucket: str, bucket_path: str, local_file_path: str
) -> None:
    """
    Upload a file to GCP.

    :param storage_client: The GCP storage client object
    :type storage_client: [type]
    :param bucket: The bucket name of the file to upload to
    :type bucket: str
    :param bucket_path: The path within the bucket to upload the file.
    :type bucket_path: str
    :param local_file_path: The local file path to upload the file to
    :type local_file_path: str
    """
    with open(local_file_path, "rb") as input_file:
        storage_client.get_bucket(bucket).blob(bucket_path).upload_from_file(input_file)
