import asyncio
import json
import logging
import sys
from dataclasses import dataclass
import argparse


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
    parser = argparse.ArgumentParser(description='Python binding KCP tunnel {}.'.format('Local' if is_local else 'Server'))
    parser.add_argument('-s', '--server', help='Host name or IP address of your remote server.', required=True)
    parser.add_argument('-p', '--server_port', help='Port number of your remote server.', required=True, type=int)
    parser.add_argument('-l', '--local', help='Host name or IP address your local server', required=True)
    parser.add_argument('-t', '--local_port', help='Port number of your local server.', required=True, type=int)
    parser.add_argument('-m', '--mtu', help='Maximum Transmission Unit for UDP packets (default: 1350)', default=1350)
    parser.add_argument('-i', '--interval', help='Interval of KCP update (ms)', type=int, default=50,
                        choices=[30, 40, 50])
    parser.add_argument('--nodelay', help='KCP ack nodelay or delay', action='store_true')
    parser.add_argument('-r', '--resend', help='Fast resend', default=0, choices=[0, 1, 2])
    parser.add_argument('--nc', help="enable net control", action='store_false')
    parser.add_argument('-c', '--config', help='config file path')
    args = parser.parse_args()
    if args.config:
        try:
            with open(args.config) as file:
                try:
                    config_dict = json.load(file)
                    return KCPConfig(**config_dict)
                except ValueError:
                    logging.exception("error format of config file")
                    exit(1)
        except IOError:
            logging.exception("error loading config file")
            exit(1)
    return args
    # if is_local:
    #     return KCPConfig(**{
    #         'server': '127.0.0.1',
    #         'server_port': 8002,
    #         'local_address': '127.0.0.1',
    #         'local_port': 8001,
    #         'interval': 50,
    #         'nodelay': 1,
    #         'nc': 1,
    #         'resend': 2,
    #         'mtu': 1250,
    #     })
    # else:
    #     return KCPConfig(**{
    #         'server': '127.0.0.1',
    #         'server_port': 8003,
    #         'local_address': '127.0.0.1',
    #         'local_port': 8002,
    #         'interval': 50,
    #         'nodelay': 1,
    #         'nc': 1,
    #         'resend': 2,
    #         'mtu': 1250,
    #     })
