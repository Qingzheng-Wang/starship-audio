# Copyright (c) 2022 David Chan
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

import time

import requests
from absl import app, flags, logging

flags.DEFINE_string("server_ip", None, "The IP of the server to connect to")

FLAGS = flags.FLAGS


def main(*unused_argv):
    while True:
        # Get the status
        r = requests.get(f"http://{FLAGS.server_ip}/status")
        if r.status_code != 200:
            logging.error("Failed to get status from server")
            time.sleep(5)
            continue
        status = r.json()
        print(status)
        time.sleep(5)


if __name__ == "__main__":
    app.run(main)
