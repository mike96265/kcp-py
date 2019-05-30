import asyncio
import logging

from kcp_manager import KCPServerManager

logger = logging.getLogger(__name__)


async def wait(coro, flag):
    return await coro, flag


class ServerProxy:

    async def start_serve(self, local_addr, remote_addr, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.manager = KCPServerManager(loop)
        await loop.create_datagram_endpoint(self.manager, local_addr=local_addr)
        self.remote_addr = remote_addr
        await self.manager.start_serve(self.proxy)

    async def proxy(self, reader, writer):
        ur, uw = await asyncio.open_connection(self.remote_addr[0], self.remote_addr[1], loop=self.loop)
        pending = {
            wait(reader.read(1024), 'rr'),
            wait(ur.read(1024), 'ur')
        }
        try:
            while True:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                    loop=self.loop
                )
                for task in done:
                    data, flag = task.result()
                    if flag == 'rr':
                        if data:
                            uw.write(data)
                            pending.add(wait(uw.drain(), 'uw'))
                            pending.add(wait(reader.read(1024), 'rr'))
                        else:
                            raise Exception
                    elif flag == 'ur':
                        if data:
                            writer.write(data)
                            pending.add(wait(ur.read(1024), 'ur'))
                            pending.add(wait(writer.drain(), 'ww'))
                        else:
                            raise Exception
                    else:
                        pass
        except (asyncio.CancelledError, Exception) as err:
            logger.error(err)
        finally:
            uw.close()
            writer.close()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    server = ServerProxy()
    coro = server.start_serve(('127.0.0.1', 8888), ('127.0.0.1', 9999), loop)
    loop.create_task(coro)
    try:
        loop.run_forever()
    finally:
        loop.close()
