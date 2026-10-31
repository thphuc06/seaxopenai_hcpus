"""Reset a running demo through its role-checked API; never starts a server."""
from __future__ import annotations

import argparse
from collections.abc import Sequence

import httpx


def reset_demo(client: httpx.Client) -> int:
    try:
        response = client.post("/api/internal/demo/reset", headers={
            "X-Demo-Role": "OPERATOR", "X-Demo-Actor": "demo-reset-cli",
        })
        response.raise_for_status()
    except httpx.RequestError:
        print("Demo server is not reachable. Start the backend Action and check --base-url.")
        return 1
    except httpx.HTTPStatusError as error:
        print(f"Demo reset failed: HTTP {error.response.status_code}.")
        return 1
    print("Demo reset completed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.base_url, timeout=10.0, follow_redirects=False) as client:
        return reset_demo(client)


if __name__ == "__main__":
    raise SystemExit(main())
