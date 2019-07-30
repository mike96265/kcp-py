import logging
import sys
from dataclasses import dataclass


def check_python():
    info = sys.version_info
    if info[0] != 3 and info[1] < 7:
        print('Python 3.7+ required')
        sys.exit(1)


@dataclass
class KCPConfig:
    server: str
    server_port: int
    local_address: str
    local_port: int
    mtu: int
    interval: int
    nodelay: bool
    nc: int
    resend: int


def get_config(is_local):
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-s: %(message)s')
    if is_local:
        return KCPConfig(**{
            'server': '127.0.0.1',
            'server_port': 8002,
            'local_address': '127.0.0.1',
            'local_port': 8001,
            'interval': 50,
            'nodelay': 1,
            'nc': 1,
            'resend': 2,
            'mtu': 1250,
        })
    else:
        return KCPConfig(**{
            'server': '127.0.0.1',
            'server_port': 8003,
            'local_address': '127.0.0.1',
            'local_port': 8002,
            'interval': 50,
            'nodelay': 1,
            'nc': 1,
            'resend': 2,
            'mtu': 1250,
        })
