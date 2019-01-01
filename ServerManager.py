import asyncio
from asyncio import AbstractEventLoop, DatagramProtocol, Future, Queue
from collections import defaultdict
from typing import Union, Text, Tuple

from KCP import KCP
from common import AbstractManager


class ServerManager(AbstractManager):

    def __init__(self, local_addr: Tuple[str, int], loop: AbstractEventLoop = None):
        self.local_addr = local_addr
        self.loop = loop or asyncio.get_event_loop()
        self.transport, self.protocol = None, None
        self.connections = {}
        self.recv_wait = defaultdict(Future)
        self.remote_addr = None
        self.wait_accept = Queue()

    async def start(self):
        self.transport, self.protocol = await self.loop.create_datagram_endpoint(
            lambda: ServerProtocol(self), local_addr=self.local_addr
        )
        self.loop.create_task(self.interval())

    async def accept(self):
        return await self.wait_accept.get()


class ServerProtocol(DatagramProtocol):

    def __init__(self, manager: ServerManager):
        self.manager = manager
        self.transport = None

    def connection_made(self, transport: DatagramProtocol):
        self.transport = transport

    def datagram_received(self, data: Union[bytes, Text], addr: Tuple[str, int]):
        if not self.manager.remote_addr:
            self.manager.remote_addr = addr
        conv = KCP.ikcp_decode32u(data, 0)
        if conv not in self.manager.connections:
            kcp = self.manager.get_session(conv)
            self.manager.loop.create_task(self.manager.wait_accept.put(kcp))
        self.manager.input(conv, data)
