import asyncio
import logging

from kcp_manager import KCPClientManager

logger = logging.getLogger(__name__)


async def wait(coro, flag):
    return await coro, flag


class ClientProxy:
    manager: KCPClientManager = None

    async def start_serve(self, listen_addr, remote_addr, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.manager = KCPClientManager(loop, remote_addr=remote_addr)
        await loop.create_datagram_endpoint(self.manager, remote_addr=remote_addr)
        server = await asyncio.start_server(self.proxy, listen_addr[0], listen_addr[1], loop=loop)
        return server

    async def proxy(self, reader, writer):
        ur, uw = await self.manager.open_connection()
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
    client = ClientProxy()
    coro = client.start_serve(('127.0.0.1', 7777), ('127.0.0.1', 8888), loop=loop)
    loop.create_task(coro)
    try:
        loop.run_forever()
    finally:
        loop.close()
