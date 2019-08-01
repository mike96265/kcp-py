import codecs
from setuptools import setup

setup(
    name='kcp_py',
    version='0.0.1',
    description='Python binding KCP tunnel',
    author='luvjoey1996',
    author_email='luvjoey1996@gmail.com',
    url='https://github.com/yukityan/kcp-py',
    packages=['kcp'],
    package_data={
      'kcp': ['KCP.cpython-37m-x86_64-linux-gnu.so']
    },
    install_requires=[],
    entry_points="""
    [console_scripts]
    kcp_local = kcp.local:main
    kcp_server = kcp.server:main
    """,
    classifiers=[
        'Programming Language :: Python :: 3.7'
    ]
)
