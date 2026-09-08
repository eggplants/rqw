"""Command line entry point for rqw."""

from __future__ import annotations

import shutil
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace, RawDescriptionHelpFormatter

from . import __version__


class HelpFormatter(ArgumentDefaultsHelpFormatter, RawDescriptionHelpFormatter):
    """Show argument defaults while keeping the description's own line breaks."""


def parse_args(args: list[str] | None = None) -> Namespace:
    """Parse the command line.

    Args:
        args: Arguments to parse instead of `sys.argv[1:]`. Used by the tests.

    Returns:
        The parsed arguments.
    """
    parser = ArgumentParser(
        prog="rqw",
        description="SPARQL Endpoint interface, compatible with SPARQLWrapper.",
        formatter_class=lambda prog: HelpFormatter(
            prog,
            width=shutil.get_terminal_size(fallback=(120, 50)).columns,
            max_help_position=40,
        ),
    )
    parser.add_argument("name", nargs="?", default="world", help="who to greet")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(args)


def main(args: list[str] | None = None) -> None:
    """Run the command."""
    parsed = parse_args(args)
    print(f"Hello, {parsed.name}!")


if __name__ == "__main__":
    main()
