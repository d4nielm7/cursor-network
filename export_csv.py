import os
import json
import argparse
import asyncio
import shutil

# Reuse the existing export function and env loading from server.py
from server import export_network_csv  # type: ignore


async def run_export(output_path: str) -> int:
    """
    Call export_network_csv() and copy the CSV to output_path.
    Returns 0 on success, non-zero on failure.
    """
    try:
        # Call export function (no parameters)
        result_json = await export_network_csv()

        # Parse the result
        result = json.loads(result_json)

        status = result.get("status")
        if status != "success":
            message = result.get("message", "Unknown error")
            print(f"Export failed: {message}")
            return 2

        # The export function always saves to data/network.csv
        src_path = "data/network.csv"
        
        if os.path.isfile(src_path):
            # Copy to requested output path if different
            if output_path != src_path:
                os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
                shutil.copy2(src_path, output_path)
                final_path = output_path
            else:
                final_path = src_path
            
            row_count = result.get("row_count", 0)
            size_kb = result.get("size_kb")
            print(f"Saved CSV to: {final_path} ({row_count} rows, ~{size_kb} KB)")
            return 0

        print(f"Export succeeded but file not found at: {src_path}")
        return 3
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
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


