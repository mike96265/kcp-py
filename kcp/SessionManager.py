import asyncio

from kcp.UKCPFactory import UKCPConnector


class ClientSession:

    def __init__(self, local_addr, remote_addr, loop):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.loop = loop
        self.kcpConnector = UKCPConnector(loop, remote_addr)

    async def server(self):
        server = await asyncio.start_server(self.proxy, host=self.local_addr[0], port=self.local_addr[1])
        async with server:
            await server.serve_forever()

    async def proxy(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        kcpReader, kcpWriter = self.kcpConnector.connect()
        while True:
            asyncio.wait()

    async def wrap(self, flag, coro):
        return flag, await coro
