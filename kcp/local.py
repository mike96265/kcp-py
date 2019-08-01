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


async def _main():
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

    logging.info("starting local at %s:%s", config.local, config.local_port)
    updater.load_config(config)
    updater.run()
    for signame in {'SIGQUIT', 'SIGTERM'}:
        loop.add_signal_handler(
            getattr(signal, signame), lambda: asyncio.ensure_future(utils.shutdown(signame, loop)))
    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        await asyncio.sleep(1)


def main():
    asyncio.run(_main())


if __name__ == '__main__':
    main()
