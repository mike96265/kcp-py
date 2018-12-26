import asyncio

from ClientManager import ClientManager


class Client:

    def __init__(self, local_addr, remote_addr, loop=None):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.loop = loop or asyncio.get_event_loop()
        self.manager = ClientManager(remote_addr=remote_addr, loop=self.loop)

    async def start(self, **kwargs):
        self.client = await asyncio.start_server(self.dispatcher, host=self.local_addr[0],
                                                 port=self.local_addr[1], loop=self.loop)
        await self.manager.start()

    async def dispatcher(self, reader, writer):
        kcp = self.manager.get_session()
        pending = {
            self.manager.recv(kcp),
            self.read(reader)
        }
        try:
            while True:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                    loop=self.loop
                )
                for task in done:
                    flag, data = task.result()
                    if flag == 'recv':
                        writer.write(data)
                        await writer.drain()
                        pending.add(self.manager.recv(kcp))
                    elif flag == 'read':
                        self.manager.send(kcp, data)
                        pending.add(self.read(reader))
                    else:
                        pass
        except (asyncio.CancelledError, Exception) as err:
            print(err)
        finally:
            writer.close()
            self.manager.close(kcp)

    async def read(self, reader):
        return 'read', (await reader.read(1024))


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    client = Client(('127.0.0.1', 7777), ('127.0.0.1', 8888), loop)
    loop.run_until_complete(client.start())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.close()
