import argparse
import asyncio
import functools
import json
import logging
import sys
from dataclasses import dataclass


def check_python():
    info = sys.version_info
    if info[0] != 3 and info[1] < 7:
        print('Python 3.7+ required')
        sys.exit(1)


async def shutdown(signame, loop):
    logging.info('caught {0}'.format(signame))
    tasks = [task for task in asyncio.Task.all_tasks() if task is not
             asyncio.tasks.Task.current_task()]
    list(map(lambda task: task.cancel(), tasks))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    logging.info('finished awaiting cancelled tasks, results: %s'.format(results))
    loop.stop()


def singleton(cls):
    instance = None

    @functools.wraps(cls)
    def wrapper(*args, **kwargs):
        nonlocal instance
        if not instance:
            instance = cls(*args, **kwargs)
        return instance

    return wrapper


@singleton
@dataclass
class KCPConfig:
    server: str
    server_port: int
    local: str
    local_port: int
    sndwnd: int
    rcvwnd: int
    mtu: int
    interval: int
    nodelay: bool
    nc: int
    resend: int


def get_config(is_local):
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-s: %(message)s')
    parser = argparse.ArgumentParser(
        description='Python binding KCP tunnel {}.'.format('Local' if is_local else 'Server'))
    config_attr = ['server', 'server_port', 'local', 'local_port',
                   'sndwnd', 'rcvwnd', 'mtu',
                   'interval', 'nodelay', 'resend', 'nc']
    parser.add_argument('-s', '--server', help='Host name or IP address of your remote server.')
    parser.add_argument('-p', '--server_port', help='Port number of your remote server.', type=int)
    parser.add_argument('-l', '--local', help='Host name or IP address your local server')
    parser.add_argument('-t', '--local_port', help='Port number of your local server.', type=int)
    parser.add_argument('-c', '--config', help='config file path')
    parser.add_argument(
        '--sndwnd',
        help='send window size. (default 128)',
        type=int,
        default=128)
    parser.add_argument(
        '--rcvwnd',
        help='receive window size (default 512)',
        type=int,
        default=512)
    parser.add_argument(
        '--mtu',
        help='Maximum Transmission Unit for UDP packets (default: 1350)',
        type=int,
        default=1350)
    parser.add_argument(
        '--interval',
        help='Interval of KCP update (ms)',
        type=int,
        default=50,
        choices=[10, 20, 30, 40, 50])
    parser.add_argument(
        '--nodelay',
        help='KCP ack nodelay or delay (default: 0 nodelay)',
        type=int,
        choices=[0, 1],
        default=0)
    parser.add_argument(
        '--resend',
        help='Fast resend',
        type=int,
        default=0,
        choices=[0, 1, 2])
    parser.add_argument(
        '--nc',
        help="net control disable or enable (default: 0 enable)",
        type=int,
        default=0,
        choices=[0, 1])
    args = parser.parse_args()
    if args.config:
        try:
            with open(args.config) as file:
                try:
                    args_list = []
                    config_dict = json.load(file)
                    for k, v in config_dict.items():
                        args_list.append(f'--{k}')
                        args_list.append(f'{v}')
                    args = parser.parse_args(args_list)
                except ValueError:
                    logging.exception("error format of config file")
                    exit(1)
        except IOError:
            logging.exception("error loading config file")
            exit(1)
    return KCPConfig(**{k: getattr(args, k) for k in config_attr})
