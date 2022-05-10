# Starship

Starship is an auto-scaling GCP-based youtube download tool, which spins up a server instance, and multiple worker
instances to avoid the youtube download rate limit restrictions.

## Usage

To use starship, make sure you are authorized with GCP (you can run gsutil commands from the terminal) and be sure that
the local machine has been added to the firewall exceptions on GCP (for polling the server instance).

Next, create a list of YouTube video IDs that you would like to download. Each line in the txt file should have a single
YouTube video ID, and should be newline terminated. The data can also contain a CSV, with the VideoID, Start time and
End time specified as the three columns. If this is specified, the data will be automatically clipped (to save space).

Finally, create a GCP bucket containing a "videos" folder. This is where the final data will be dumped (as well as some
additional files for communication between the processes).

Then, you can run the command below to launch a download instance:

```bash
>> python app.py --gcp_project=[YOUR PROJECT NAME] --num_workers=195 --input=data.txt --zones=us-east1-b,us-east4-c,us-west2-a,europe-west1-b,europe-west2-a,europe-west4-a --max_workers_per_zone=70 --bucket=[YOUR BUCKET NAME]
```

The above command will launch a download with 195 workers and 1 server instance spread across three compute zones, with
70 instances per zone. At maximum, you should use 72 workers per zone, since the default GCP quota is 72 vCPUs per compute
region.

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
