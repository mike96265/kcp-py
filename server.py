import asyncio
import logging

import uvloop

from kcp_manager import KCPServerManager
from pipe import Pipe

logger = logging.getLogger(__name__)


class ServerProxy:

    def __init__(self, local_addr, remote_addr, loop=None):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.loop = loop or asyncio.get_event_loop()
        self.manager = KCPServerManager(loop)

    async def start_serve(self):
        self.loop = loop or asyncio.get_event_loop()
        await loop.create_datagram_endpoint(self.manager, local_addr=self.local_addr)
        await self.manager.start_serve(self.proxy)

    async def proxy(self, kcp_reader, kcp_writer):
        app_reader, app_writer = await asyncio.open_connection(self.remote_addr[0], self.remote_addr[1], loop=self.loop)
        try:
            pipe1 = Pipe(kcp_reader, app_writer, 1400)
            pipe2 = Pipe(app_reader, kcp_writer, 1400)
            await asyncio.gather(pipe1.open(), pipe2.open())
        except (asyncio.CancelledError, Exception) as err:
            logger.error(err)
        finally:
            app_writer.close()
            kcp_writer.close()


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()
    server = ServerProxy(('127.0.0.1', 8888), ('127.0.0.1', 1080), loop)
    coro = server.start_serve()
    loop.create_task(coro)
    try:
        loop.run_forever()
    finally:
        loop.close()
