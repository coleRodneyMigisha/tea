"""tea: prepares weekly blog posts for Medium."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tea")
except PackageNotFoundError:  # run from a checkout that was never installed
    __version__ = "0.1.0"
