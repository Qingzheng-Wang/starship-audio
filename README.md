# Starship

Starship is an auto-scaling GCP-based video download tool, which spins up a server instance, and multiple worker
instances for faster downloading of video.

## Usage

To use starship, make sure you are authorized with GCP (you can run gsutil commands from the terminal) and be sure that
the local machine has been added to the firewall exceptions on GCP (for polling the server instance).

Next, follow the File Input Format instructions below to create a JSON file describing the videos to be downloaded.

Finally, create a GCP bucket. This is where the final data will be dumped (as well as some
additional files for communication between the processes).

Then, you can run the command below to launch a download instance:

```bash
>> python app.py --gcp_project=[YOUR PROJECT NAME] --num_workers=408 --input=data.json --zones=us-east1-b,us-east4-c,us-west2-a,europe-west1-b,europe-west2-a,europe-west4-a --max_workers_per_zone=68 --bucket=[YOUR BUCKET NAME]
```

The above command will launch a download with 408 workers and 1 server instance spread across six compute zones, with
68 instances per zone. At maximum, you should use 68 workers per zone, since the default GCP quota for IP addresses is
69 per region.

## File Input Format

The files should be input in a JSON file with the following format:

```json
[
    {
        "url": "https://...",
        "output_path": "Local bucket path to upload files",
        "postprocessing": "(optional) ffmpeg -i <what you would put here>",
        "postprocessing_output": "(optional) if you have a -o in postprocessing, what that is",
        "ytdl_opts": {
            "outtmpl": "(optional) Note: Outtmpl must start with ./videodata/",
            "...": "(Optional) Overrides for ytdl download process"
        }
    }
]
```
