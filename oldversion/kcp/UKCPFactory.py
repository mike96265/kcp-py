import asyncio
import functools
from asyncio import StreamReader, StreamWriter
from collections import namedtuple

from .KCP import KCP

_DEFAULT_LIMIT = 2 ** 16  # 64 KiB


class UKcp(KCP):

    def __init__(self, conv, udp):
        super(UKcp, self).__init__(conv)
        self.udp = udp

    def output(self, buffer: bytearray, size):
        self.udp.output(buffer, size)


UKcpStruct = namedtuple('UkcpStruct', ('conn', 'reader', 'writer'))


class TransportWrapper:

    def __init__(self, conv, factory):
        self._conv = conv
        self._factory = factory

    def __getattr__(self, item):
        return getattr(self._factory.transport, item)

    def write(self, data):
        self._factory.send(self._conv, data)


Conn = namedtuple('Conn', ('kcpConn', 'reader', 'writer'))


class UKCPFactory:
    conns = {}
    activeConns = set()
    conv = 1
    updateSchedule = {}

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def interval(self):
        for conv in self.activeConns:
            self.update(conv)
        self.activeConns = set()
        self._loop.call_later(0.05, self.interval)

    def update(self, conv):
        kcpConn, reader, _ = self.conns[conv]
        current = int(self._loop.time() * 1000)
        kcpConn.update(current)
        if kcpConn.state == -1:
            reader.feed_eof()
        peeksize = kcpConn.peeksize()
        if peeksize not in (0, -1):
            data = kcpConn.recv(peeksize)
            reader.feed_data(data)
        next_call = kcpConn.check(current)
        schedule = self._loop.call_later(next_call / 1000, functools.partial(self.update, conv))
        self.updateSchedule[conv] = schedule


class UKCPConnector(asyncio.DatagramProtocol, UKCPFactory):

    def __init__(self, loop: asyncio.AbstractEventLoop, remote_addr=None):
        UKCPFactory.__init__(self, loop)
        self.connecting = asyncio.Event()
        self._remote_addr = remote_addr
        self._loop.create_datagram_endpoint(self, remote_addr=remote_addr)

    def connection_made(self, transport) -> None:
        self.connecting.set()
        self._transport = transport

    def datagram_received(self, data, addr):
        conv = UKcp.ikcp_decode32u(data, 0)
        if conv in self.conns:
            self.activeConns.add(conv)
            self.conns[conv].kcpConn.input(data)

    def output(self, buffer, size):
        self._transport.sendto(buffer[:size], self._remote_addr)

    def send(self, conv, data):
        self.activeConns.add(conv)
        self.conns[conv].send(data)

    async def connect(self):
        await self.connecting.wait()
        kcpConn = UKcp(self.conv, self)
        reader = StreamReader(limit=_DEFAULT_LIMIT, loop=self._loop)
        writer = StreamWriter(TransportWrapper(self.conv, self), self, reader, self._loop)
        conn = Conn(kcpConn=kcpConn, reader=reader, writer=writer)
        self.conns[self.conv] = conn
        self.activeConns.add(self.conv)
        self.conv += 1
        return reader, writer

    def __call__(self, *args, **kwargs):
        return self


class UKCPListener(asyncio.DatagramProtocol, UKCPFactory):
    cb = None
    default_receiver = None

    def __init__(self, loop: asyncio.AbstractEventLoop, local_addr=None):
        UKCPFactory.__init__(self, loop)
        self.connecting = asyncio.Event()
        self._local_addr = local_addr
        self._loop.create_datagram_endpoint()

    def connection_made(self, transport) -> None:
        self.connecting.set()
        self._transport = transport

    def datagram_received(self, data, addr):
        self.default_receiver = addr
        conv = UKcp.ikcp_decode32u(data, 0)
        if conv in self.conns:
            self.activeConns.add(conv)
            self.conns[conv].kcpConn.input(data)
        else:
            kcpConn = UKcp(conv, self)
            reader = StreamReader(limit=_DEFAULT_LIMIT, loop=self._loop)
            writer = StreamWriter(TransportWrapper(conv, self), self, reader, self._loop)
            conn = Conn(kcpConn=kcpConn, reader=reader, writer=writer)
            self.conns[conv] = conn
            self.activeConns.add(conv)
            self._loop.create_task(self.cb(reader, writer))

    def output(self, buffer, size):
        self._transport.sendto(buffer[:size], self.default_receiver)

    def send(self, conv, data):
        self.activeConns.add(conv)
        self.conns[conv].send(data)

    async def listen(self, cb):
        await self.connecting
        self.cb = cb
