"""Run the commands shown in README.md and compare them with the output printed there.

Every ```console block in the README is a transcript: `$ invoice-agent ...` lines (with `\\`
continuations) followed by the exact output. The quickstart's `invoice-agent eval` runs too. If
the README drifts from what the tool prints, this test fails.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from invoice_agent.cli import main

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def _blocks(lang: str) -> list[str]:
    text = README.read_text(encoding="utf-8")
    return re.findall(rf"^```{lang}\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)


def _transcripts() -> list[tuple[list[str], str]]:
    out: list[tuple[list[str], str]] = []
    for block in _blocks("console"):
        lines = block.splitlines()
        assert lines[0].startswith("$ "), "a console block must start with a $ command"
        command = lines[0][2:]
        i = 1
        while command.endswith("\\"):
            command = command[:-1] + " " + lines[i].strip()
            i += 1
        out.append((shlex.split(command), "\n".join(lines[i:]) + "\n"))
    return out


TRANSCRIPTS = _transcripts()


def test_readme_has_transcripts() -> None:
    assert len(TRANSCRIPTS) >= 2


@pytest.mark.parametrize(
    ("argv", "expected"), TRANSCRIPTS, ids=[f"console-{i}" for i in range(len(TRANSCRIPTS))]
)
def test_readme_console_block(
    argv: list[str],
    expected: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert argv[0] == "invoice-agent"
    monkeypatch.chdir(ROOT)
    assert main(argv[1:]) == 0
    assert capsys.readouterr().out == expected


def test_readme_quickstart(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    quickstart = README.read_text(encoding="utf-8").split("## Quickstart", 1)[1]
    block = re.search(r"```sh\n(.*?)```", quickstart, flags=re.DOTALL)
    assert block is not None
    commands = [c for c in block.group(1).splitlines() if c.startswith("invoice-agent ")]
    assert commands == ["invoice-agent eval"]
    monkeypatch.chdir(ROOT)
    assert main(shlex.split(commands[0])[1:]) == 0
    out = capsys.readouterr().out
    assert "Decision accuracy" in out
