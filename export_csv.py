import os
import json
import base64
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
        result_json = await export_network_csv()

        # If server returned a python dict as str, ensure it's parsed
        result = json.loads(result_json)

        status = result.get("status")
        if status != "success":
            message = result.get("message", "Unknown error")
            print(f"Export failed: {message}")
            return 2

        b64 = result.get("csv_base64")
        if not b64:
            print("Export failed: csv_base64 missing in response")
            return 3

        csv_bytes = base64.b64decode(b64)

        # Ensure output dir exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(csv_bytes)

        row_count = result.get("row_count", 0)
        size_kb = result.get("size_kb")
        print(f"Saved CSV to: {output_path} ({row_count} rows, ~{size_kb} KB)")
        return 0
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


