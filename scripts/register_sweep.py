"""Replace the system cron entry with an Infrai scheduled webhook."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from infrai_client import InfraiClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Register or remove the property cleanup schedule")
    parser.add_argument("--delete", metavar="JOB_ID")
    args = parser.parse_args()
    client = InfraiClient(os.environ["INFRAI_API_KEY"])
    if args.delete:
        client.delete_cron(args.delete)
        print(f"Removed property cleanup schedule: {args.delete}")
        return
    task_url = os.environ["CLEANUP_TASK_URL"].rstrip("/") + "/cleanup/sweep"
    job_id = client.create_cron("0 3 * * *", task_url)
    print(f"Scheduled daily property cleanup: {job_id}")


if __name__ == "__main__":
    main()
