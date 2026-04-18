"""Load the innomd script as a module so tests can import its functions."""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path


def load_innomd():
    path = Path(__file__).resolve().parent.parent / "innomd"
    loader = SourceFileLoader("innomd_mod", str(path))
    spec = importlib.util.spec_from_loader("innomd_mod", loader)
    assert spec and spec.loader, f"could not load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
