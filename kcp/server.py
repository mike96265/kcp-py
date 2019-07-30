import asyncio
import functools

from kcp import utils
from kcp.protocols import ServerDataGramHandlerProtocol
from kcp.pipe import open_pipe
from kcp.updater import updater


async def main():
    loop = asyncio.get_event_loop()
    config = utils.get_config(False)

    def ds_factory():
        return asyncio.open_connection(host=config.server, port=config.server_port)

    protocol = ServerDataGramHandlerProtocol(functools.partial(open_pipe, ds_factory=ds_factory))
    await loop.create_datagram_endpoint(lambda: protocol, local_addr=(config.local_address, config.local_port))
    updater.load_config(config)
    updater.run()
    e = asyncio.Event()
    await e.wait()


if __name__ == '__main__':
    asyncio.run(main())
