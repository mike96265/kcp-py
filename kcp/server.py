import asyncio
import functools
import logging
import os
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

from kcp import utils
from kcp.protocols import ServerDataGramHandlerProtocol
from kcp.pipe import open_pipe
from kcp.updater import updater


async def _main():
    loop = asyncio.get_event_loop()
    config = utils.get_config(False)

    def ds_factory():
        return asyncio.open_connection(host=config.server, port=config.server_port)

    protocol = ServerDataGramHandlerProtocol(functools.partial(open_pipe, ds_factory=ds_factory))
    await loop.create_datagram_endpoint(lambda: protocol, local_addr=(config.local, config.local_port))
    logging.info("start server at %s:%s", config.local_address, config.local_port)
    updater.load_config(config)
    updater.run()
    for signame in {'SIGQUIT', 'SIGTERM'}:
        loop.add_signal_handler(
            getattr(signal, signame), lambda: asyncio.ensure_future(utils.shutdown(signame, loop)))
    e = asyncio.Event()
    await e.wait()


def main():
    asyncio.run(_main())


if __name__ == '__main__':
    main()
