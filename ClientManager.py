import asyncio
from asyncio import AbstractEventLoop, DatagramProtocol, BaseTransport, Queue, Future
from collections import defaultdict
import logging
from typing import Union, Text, Tuple

from KCP import KCP
from common import current

logger = logging.getLogger(__name__)

TWELVE_HOUR = 12 * 60 * 60 * 1000


class UKCP(KCP):

    def __init__(self, conv, manager: 'AbstractManager'):
        super(UKCP, self).__init__(conv)
        self.manager = manager

    def output(self, buffer: bytearray, size):
        self.manager.output(buffer[:size])

    def __lt__(self, other: 'UKCP'):
        _current = current()
        return self.check(_current) < other.check(_current)

    def __eq__(self, other: 'UKCP'):
        _current = current()
        return self.check(_current) == other.check(_current)

    def __gt__(self, other: 'UKCP'):
        _current = current()
        return self.check(_current) > other.check(_current)


class AbstractManager:

    def output(self, buffer):
        self.transport.sendto(buffer, addr=self.remote_addr)

    def input(self, conv: int, data: Union[bytearray, bytes] = None):
        kcp = self.connections.get(conv)
        kcp.input(data)

    async def recv(self, kcp):
        data = await self.recv_wait[kcp.conv]
        self.recv_wait[kcp.conv] = Future()
        return 'recv', data

    def send(self, kcp, data):
        kcp.send(data)

    async def interval(self):
        while True:
            await asyncio.sleep(0.1)
            for i in self.connections.values():
                i.update(current())
                data = i.recv()
                if data != -2 and data:
                    if self.recv_wait[i.conv].done():
                        self.recv_wait[i.conv].result()[-1:] = data
                    else:
                        self.recv_wait[i.conv].set_result(data)

    def get_session(self, conv=None):
        if conv is not None:
            conv = conv
        else:
            conv = self.conv
        kcp = UKCP(conv, self)
        kcp.update(current())
        self.connections[conv] = kcp
        return kcp


class ClientManager(AbstractManager):

    def __init__(self, remote_addr=Tuple[str, int], loop: AbstractEventLoop = None):
        self.remote_addr = remote_addr
        self.loop = loop or asyncio.get_event_loop()
        self.transport, self.protocol = None, None
        self.connections = {}
        self.recv_wait = defaultdict(Future)
        self._conv_generator = (i for i in range(TWELVE_HOUR))

    async def start(self):
        self.transport, self.protocol = await self.loop.create_datagram_endpoint(
            lambda: ClientProtocol(self),
            remote_addr=self.remote_addr)
        await self.loop.create_task(self.interval())

    @property
    def conv(self):
        while True:
            try:
                return next(self._conv_generator)
            except StopIteration:
                self._conv_generator = (i for i in range(TWELVE_HOUR))


class ClientProtocol(DatagramProtocol):

    def __init__(self, manager: ClientManager):
        self.manager = manager
        self.transport = None

    def connection_made(self, transport: DatagramProtocol):
        logger.info('connecting to server %s:%s', *self.manager.remote_addr)
        self.transport = transport

    def datagram_received(self, data: Union[bytes, Text], addr: Tuple[str, int]):
        conv = KCP.ikcp_decode32u(data, 0)
        if conv in self.manager.connections:
            self.manager.input(conv, data)


class ServerManager(AbstractManager):

    def __init__(self, local_addr: Tuple[str, int], loop: AbstractEventLoop = None):
        self.local_addr = local_addr
        self.loop = loop or asyncio.get_event_loop()
        self.transport, self.protocol = None, None
        self.connections = {}
        self.recv_wait = defaultdict(Future)
        self.remote_addr = None
        self.wait_accept = Future()

    async def start(self):
        self.transport, self.protocol = await self.loop.create_datagram_endpoint(
            lambda: ServerProtocol(self), local_addr=self.local_addr
        )
        self.loop.create_task(self.interval())

    async def accept(self):
        accept = await self.wait_accept
        self.wait_accept = Future()
        return accept


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
            self.manager.wait_accept.set_result(kcp)
        self.manager.input(conv, data)
