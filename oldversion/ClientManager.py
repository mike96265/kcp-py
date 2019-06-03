import asyncio
import logging
from asyncio import AbstractEventLoop, DatagramProtocol, Future
from collections import defaultdict
from typing import Union, Text, Tuple

from oldversion.KCP import KCP
from oldversion.common import AbstractManager

logger = logging.getLogger(__name__)

TWELVE_HOUR = 12 * 60 * 60 * 1000


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
