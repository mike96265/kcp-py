from setuptools import setup, Extension
from Cython.Build import cythonize

ext = Extension("KCP", sources=["kcp/KCP.pyx", "ikcp/ikcp.c"])

core = cythonize(ext)

setup(
    ext_modules=core,
)
