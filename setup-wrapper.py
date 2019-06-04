from setuptools import setup, Extension
from Cython.Build import cythonize

ext = Extension("KCPWrapper", sources=["KCPWrapper.pyx", "ikcp.c"])

core = cythonize(ext)

setup(
    ext_modules=core,
)
