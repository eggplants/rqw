from __future__ import annotations

import pytest

from rqw import __version__
from rqw.cli import main


def test_version_is_available():
    assert __version__


def test_greets_the_default_name(capsys):
    main([])
    assert capsys.readouterr().out == "Hello, world!\n"


def test_greets_a_given_name(capsys):
    main(["eggplant"])
    assert capsys.readouterr().out == "Hello, eggplant!\n"


def test_version_flag_prints_the_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out
