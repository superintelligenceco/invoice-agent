"""MkDocs hook: fill `<!-- cli-help: ARGS -->` with the real `invoice-agent ARGS --help` output."""

from __future__ import annotations

import contextlib
import io
import re
from typing import Any

from invoice_agent.cli import main

MARKER = re.compile(r"<!-- cli-help:(?P<args>[^>]*)-->")


def _help(args: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.suppress(SystemExit):
        main([*args.split(), "--help"])
    return buf.getvalue().rstrip()


def on_page_markdown(markdown: str, **_: Any) -> str:
    return MARKER.sub(lambda m: f"```text\n{_help(m.group('args'))}\n```", markdown)
