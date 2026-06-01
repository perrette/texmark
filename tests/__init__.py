"""Shared helpers for the test suite."""
import shutil


def pandoc_available():
    """True if pandoc can be invoked, via PATH or the pypandoc_binary wheel."""
    if shutil.which("pandoc") is not None:
        return True
    # pypandoc_binary ships the binary inside the package (not on PATH);
    # pypandoc finds it via get_pandoc_path().
    try:
        import pypandoc
        pypandoc.get_pandoc_path()
        return True
    except Exception:
        return False
