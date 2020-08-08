#!/usr/bin/env python
import os.path
from setuptools import setup

# This is not a real version number -- it is used for testing
version = "0.1.0"
with open("./python/lsst/pex/config/version.py", "w") as f:
    print(f"""
__all__ = ("__version__", )
__version__ = '{version}'""", file=f)

# read the contents of our README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "README.rst"), encoding='utf-8') as f:
    long_description = f.read()

setup(
    version=f"{version}",
    long_description=long_description,
    long_description_content_type="text/x-rst"
)
