"""Argument parsing, single-instance handling and app start."""

import argparse
import sys
from collections.abc import Sequence

PACKET_KINDS = ("weekly", "weekly_pick", "improve")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tea", description="Prepares weekly blog posts for Medium."
    )
    parser.add_argument(
        "--background", action="store_true", help="start hidden in the tray (autostart)"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    packet = sub.add_parser("packet", help="print a packet to stdout (dev)")
    packet.add_argument("--week", metavar="YYYY-MM-DD", help="week start date")
    packet.add_argument("--kind", choices=PACKET_KINDS, help="hand-off kind")

    import_reply = sub.add_parser("import-reply", help="import a reply from a file")
    import_reply.add_argument("file", metavar="FILE", help="file holding the pasted reply")
    import_reply.add_argument("--handoff", type=int, metavar="ID", help="hand-off id")

    sub.add_parser("login-questions", help="show the question popup now")
    sub.add_parser("install-autostart", help="install launcher and autostart entries")
    sub.add_parser("uninstall-autostart", help="remove launcher and autostart entries")
    sub.add_parser("doctor", help="check tray, notification service, fonts, DB, templates, prompts")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    name = args.command or ("background" if args.background else "app")
    print(f"{name}: not implemented yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
