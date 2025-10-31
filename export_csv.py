import os
import json
import argparse
import asyncio

# Reuse the existing export function and env loading from server.py
from server import export_network_csv  # type: ignore


async def run_export(output_path: str) -> int:
    """
    Call export_network_csv() and write the decoded CSV to output_path.
    Returns 0 on success, non-zero on failure.
    """
    try:
        # Ask server to write directly to the requested path
        result_json = await export_network_csv(output_path)

        # Ensure parsed
        result = json.loads(result_json)

        status = result.get("status")
        if status != "success":
            message = result.get("message", "Unknown error")
            print(f"Export failed: {message}")
            return 2

        # Confirm the file exists at the path returned
        src_path = result.get("path")
        if src_path and os.path.isfile(src_path):
            row_count = result.get("row_count", 0)
            size_kb = result.get("size_kb")
            print(f"Saved CSV to: {src_path} ({row_count} rows, ~{size_kb} KB)")
            return 0

        # If only a remote download URL is provided, guide the user
        download_url = result.get("download_url")
        if download_url:
            print("Export succeeded, but file is available via HTTP only.")
            print(f"Download from: {download_url}")
            return 0

        print("Export succeeded but no file path or download URL returned.")
        return 3
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Export LinkedIn network to CSV file")
    parser.add_argument(
        "-o",
        "--output",
        default="linkedin_network_export.csv",
        help="Output CSV file path (default: linkedin_network_export.csv)",
    )
    args = parser.parse_args()

    return asyncio.run(run_export(args.output))


if __name__ == "__main__":
    raise SystemExit(main())


