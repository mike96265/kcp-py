import asyncio
import logging

import uvloop

from kcp_manager import KCPClientManager
from pipe import Pipe

logger = logging.getLogger(__name__)


class ClientProxy:
    manager: KCPClientManager = None

    def __init__(self, local_addr, remote_addr, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.manager = KCPClientManager(loop, remote_addr=remote_addr)
        self.remote_addr = remote_addr
        self.local_addr = local_addr

    async def start_serve(self):
        await loop.create_datagram_endpoint(self.manager, remote_addr=self.remote_addr)
        server = await asyncio.start_server(self.proxy, self.local_addr[0], self.local_addr[1], loop=loop)
        return server

    async def proxy(self, app_reader, app_writer):
        kcp_reader, kcp_writer = await self.manager.open_connection()
        try:
            pipe1 = Pipe(app_reader, kcp_writer, 1400)
            pipe2 = Pipe(kcp_reader, app_writer, 1400)
            await asyncio.gather(pipe1.open(), pipe2.open())
        except (asyncio.CancelledError, Exception) as err:
            logger.error(err)
        finally:
            kcp_writer.close()
            app_writer.close()


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()
    client = ClientProxy(('127.0.0.1', 7777), ('127.0.0.1', 8888), loop=loop)
    coro = client.start_serve()
    loop.create_task(coro)
    try:
        loop.run_forever()
    finally:
        loop.close()
