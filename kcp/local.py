import asyncio
import functools
import logging
import os
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

from kcp import utils
from kcp.pipe import open_pipe
from kcp.protocols import LocalDataGramHandlerProtocol
from kcp.updater import updater


class LocalServerError(Exception):
    """local server error"""


async def shutdown(signame, loop):
    logging.info('caught {0}'.format(signame))
    tasks = [task for task in asyncio.Task.all_tasks() if task is not
             asyncio.tasks.Task.current_task()]
    list(map(lambda task: task.cancel(), tasks))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    logging.info('finished awaiting cancelled tasks, results: %s'.format(results))
    loop.stop()


async def main():
    loop = asyncio.get_event_loop()
    utils.check_python()
    config = utils.get_config(True)
    _, protocol = await loop.create_datagram_endpoint(
        LocalDataGramHandlerProtocol,
        remote_addr=(config.server, config.server_port)
    )

    def ds_factory():
        tunnel = protocol.tunnel
        return tunnel.create_connection()

    server = await asyncio.start_server(functools.partial(open_pipe, ds_factory=ds_factory), host=config.local_address,
                                        port=config.local_port)

    logging.info("starting local at %s:%s", config.local_address, config.local_port)
    for signame in {'SIGQUIT', 'SIGTERM'}:
        loop.add_signal_handler(
            getattr(signal, signame), lambda: asyncio.ensure_future(shutdown(signame, loop)))
    updater.load_config(config)
    updater.run()
    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(main())
