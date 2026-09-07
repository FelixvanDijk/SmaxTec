"""Opt-in developer verification of the live adapter. Never run in CI."""

import argparse
import getpass
import sys
from threading import Event

from smaxtec.adapters.smaxtec.login import LoginSettings, SmaxtecLoginSession
from smaxtec.application.login import Credentials, LoginError
from smaxtec.main import configure_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--headless", action="store_true", help="No interactive verification window."
    )
    args = parser.parse_args()
    if not sys.stdin.isatty():
        print("Run this command interactively so credentials can be entered without echo.")
        return 2
    configure_runtime()
    username = getpass.getpass("Account (hidden): ")
    password = getpass.getpass("Password (hidden): ")
    session = SmaxtecLoginSession(LoginSettings(headless=args.headless))
    try:
        session.connect(
            Credentials(username, password),
            lambda event: print(event.stage.value, flush=True),
            Event(),
        )
        return 0
    except LoginError as error:
        print(f"Sign-in check failed: {error.code.value}")
        return 1
    except (KeyboardInterrupt, ValueError):
        print("Sign-in check cancelled or details missing.")
        return 1
    except Exception:
        print("Sign-in check could not finish. No private diagnostic details were recorded.")
        return 1
    finally:
        username = password = ""
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
