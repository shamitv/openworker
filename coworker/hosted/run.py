"""`openworker-web`: browser gateway and account administration."""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path


def _password(confirm: bool = True) -> str:
    password = getpass.getpass("Password: ")
    if confirm and password != getpass.getpass("Confirm password: "):
        raise ValueError("passwords do not match")
    return password


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="openworker-web")
    parser.add_argument("--data-dir", dest="global_data_dir", type=Path, default=Path("/var/lib/openworker-web"))
    actions = parser.add_subparsers(dest="action", required=True)
    serve = actions.add_parser("serve", help="serve the built SPA and per-user engines")
    serve.add_argument("--data-dir", type=Path)
    serve.add_argument("--spa", required=True, type=Path)
    serve.add_argument("--public-origin", required=True)
    serve.add_argument("--sandbox-provider", choices=["openshell", "seatbelt", "windows"], required=True)
    serve.add_argument("--host", default="127.0.0.1", help="bind address; 0.0.0.0 listens on all IPv4 interfaces (default: %(default)s)")
    serve.add_argument("--port", type=int, default=8766)
    users = actions.add_parser("user", help="manage password-only accounts")
    users.add_argument("--data-dir", type=Path)
    user_actions = users.add_subparsers(dest="user_action", required=True)
    user_actions.add_parser("list")
    for name in ("create", "disable", "reset-password"):
        user_actions.add_parser(name).add_argument("username")
    args = parser.parse_args(argv)
    args.data_dir = args.data_dir or args.global_data_dir

    if args.action == "user":
        from .accounts import AccountStore

        try:
            store = AccountStore(args.data_dir)
            if args.user_action == "list":
                for user in store.list_users():
                    print(f"{user['username']}\t{'enabled' if user['enabled'] else 'disabled'}\t{user['home']}")
            elif args.user_action == "create":
                store.create(args.username, _password())
                print(f"Created {args.username}; password change required at first login")
            elif args.user_action == "disable":
                store.disable(args.username)
                print(f"Disabled {args.username}")
            elif args.user_action == "reset-password":
                store.reset_password(args.username, _password())
                print(f"Reset {args.username}; password change required at next login")
        except sqlite3.Error:
            parser.error("account database operation failed")
        except (ValueError, KeyError, OSError) as exc:
            parser.error(str(exc))
        return

    if args.host not in ("127.0.0.1", "::1", "localhost", "0.0.0.0"):
        parser.error("--host must be 127.0.0.1, localhost, ::1 or 0.0.0.0")
    from .app import create_app

    try:
        app = create_app(spa=args.spa, data_dir=args.data_dir, public_origin=args.public_origin, sandbox_provider=args.sandbox_provider)
    except sqlite3.Error:
        parser.error("account database operation failed")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, ws_max_size=16 * 1024 * 1024, proxy_headers=False)


if __name__ == "__main__":
    main(sys.argv[1:])
