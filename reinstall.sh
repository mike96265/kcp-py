#! /bin/bash
pip uninstall kcp_py -y
python3 setup.py install
rm -rf build dist kcp_py.egg-info
