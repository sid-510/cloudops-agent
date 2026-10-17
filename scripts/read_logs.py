"""Read recent ERROR log entries from Cloud Logging"""

from google.cloud import logging as cloud_logging

PROJECT_ID = "cloudops-agent-sid510"


def main() -> None:
    client = cloud_logging.Client(project=PROJECT_ID)

    log_filter = (
        f'logName="projects/{PROJECT_ID}/logs/my-first-log" '
        "AND severity>=ERROR"
    )

    entries = client.list_entries(
        filter_=log_filter,
        order_by=cloud_logging.DESCENDING,
        max_results=5,
    )

    for entry in entries:
        print(entry.timestamp, entry.severity, entry.payload, entry.insert_id)


if __name__ == "__main__":
    main()