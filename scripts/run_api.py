#!/usr/bin/env python3
"""Start the REST API. Run scripts/update_data.py at least once first."""
import _bootstrap  # noqa: F401
import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("tennissharp.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
