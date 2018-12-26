import asyncio

from ServerManager import ServerManager


class Server:

    def __init__(self, local_addr, remote_addr, loop):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.loop = loop or asyncio.get_event_loop()
        self.manager = ServerManager(local_addr=local_addr, loop=self.loop)

    async def start(self):
        await self.manager.start()
        while True:
            kcp = await self.manager.accept()
            await self.loop.create_task(self.dispatcher(kcp))

    async def dispatcher(self, kcp):
        reader, writer = await asyncio.open_connection(self.remote_addr[0], self.remote_addr[1], loop=self.loop)
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
    server = Server(('127.0.0.1', 8888), ('127.0.0.1', 9999), loop)
    loop.run_until_complete(server.start())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.close()
