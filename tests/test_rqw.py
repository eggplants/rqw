from __future__ import annotations

import importlib

import rqw
import rqw.cli


def test_version_is_available():
    assert rqw.__version__


def test_every_exported_name_resolves():
    for name in rqw.__all__:
        assert getattr(rqw, name) is not None


def test_python_m_rqw_runs_the_cli():
    module = importlib.import_module("rqw.__main__")
    assert module.main is rqw.cli.main
