import asyncio
import functools
import logging
import socket
import time
from dataclasses import dataclass

from KCP import KCP

logger = logging.getLogger(__name__)


def ikcp_decode32u(p, offset):
    return (p[offset + 0] & 0xff) << 24 \
           | (p[offset + 1] & 0xff) << 16 \
           | (p[offset + 2] & 0xff) << 8 \
           | p[offset + 3] & 0xff


@dataclass
class Conversation:
    conv: int
    kcp: KCP
    downstream_reader: asyncio.StreamReader
    downstream_writer: asyncio.StreamWriter
    upstream_reader: asyncio.StreamReader
    upstream_writer: asyncio.StreamWriter


class AbstractKCPManager:
    _conv = 1
    _conns = {}
    _active_conns = set()
    _transport = None
    _update_schedule = {}

    def __init__(self, loop, remote_addr=None):
        self._pending = asyncio.Event(loop=loop)
        self.loop = loop
        self.remote_addr = remote_addr

    def interval(self):
        while self._active_conns:
            conv = self._active_conns.pop()
            self.update(conv)
        self.loop.call_later(0.05, self.interval)

    def update(self, conv):
        conversation = self._conns.get(conv)
        current = self.current()
        kcp = conversation.kcp
        cw = conversation.downstream_writer
        kcp.update(current)
        if kcp.state == -1:
            pass
        peeksize = kcp.peeksize()
        if peeksize not in (0, -1):
            data = bytes(peeksize)
            kcp.recv(data, peeksize)
            cw.write(data)
            self.loop.create_task(cw.drain())
        next_call = kcp.check(current)
        schedule = self.loop.call_later((next_call - current) / 1000, functools.partial(self.update, conv))
        self._update_schedule[conv] = schedule

    def close_conversation(self, conv):
        try:
            conversation = self._conns[conv]
            conversation.upstream_writer.close()
            conversation.downstream_writer.close()
            self._active_conns.remove(conv)
            us = self._update_schedule.get(conv)
            if us:
                us.cancel()
        finally:
            logger.info('conversation {} closed'.format(conv))

    def output(self, data, addr=None):
        print("output data {} to addr: {}".format(data, self.remote_addr))
        self._transport.sendto(data, addr)

    def connection_made(self, transport):
        self._transport = transport
        self._pending.set()

    async def upstream_waiter(self, conv, upstream_reader: asyncio.StreamReader):
        try:
            data = await upstream_reader.read(1024)
            print(type(data))
            if data:
                conversation = self._conns[conv]
                try:
                    conversation.kcp.send(data, len(data))
                except Exception as e:
                    print(e)
                self._active_conns.add(conv)
                self.loop.create_task(self.upstream_waiter(conv, upstream_reader))
        except Exception as err:
            print(err)
            self.close_conversation(conv)

    def datagram_received(self, data, addr):
        conv = ikcp_decode32u(data, 0)
        self.dispatch(conv, data, addr)

    def dispatch(self, conv, data, addr):
        raise NotImplementedError

    def create_kcp(self, conv=None, output=None):
        if conv is not None:
            kcp = KCP(conv, output)
        else:
            kcp = KCP(self._conv, output)
            self._conv += 1
        kcp.set_nodelay(1, 30, 3, 1)
        return kcp

    def create_stream(self):
        upstream, downstream = socket.socketpair()
        upstream.setblocking(False)
        downstream.setblocking(False)
        return upstream, downstream

    def current(self):
        return int(time.time() * 1000) & 0xffffffff


class KCPClientManager(AbstractKCPManager, asyncio.DatagramProtocol):

    def __init__(self, loop, remote_addr):
        super(KCPClientManager, self).__init__(loop)
        self.remote_addr = remote_addr
        self.loop.call_later(0.03, self.interval)

    def output(self, data, size, addr=None):
        print("client output")
        super(KCPClientManager, self).output(data, self.remote_addr)

    def dispatch(self, conv, data, addr):
        if conv in self._conns:
            conversation = self._conns[conv]
            conversation.kcp.input(data, len(data))
            self._active_conns.add(conv)

    async def open_connection(self):
        kcp = self.create_kcp(output=self.output)
        conv = kcp.conv
        upstream, downstream = self.create_stream()
        downstream_reader, downstream_writer = await asyncio.open_connection(sock=downstream, loop=self.loop)
        upstream_reader, upstream_writer = await asyncio.open_connection(sock=upstream, loop=self.loop)
        conversation = Conversation(conv=conv,
                                    kcp=kcp,
                                    upstream_reader=upstream_reader,
                                    upstream_writer=upstream_writer,
                                    downstream_reader=downstream_reader,
                                    downstream_writer=downstream_writer)
        self._conns[conv] = conversation
        self.loop.create_task(self.upstream_waiter(conv, downstream_reader))
        self._active_conns.add(conv)
        return upstream_reader, upstream_writer

    def __call__(self, *args, **kwargs):
        return self


class KCPServerManager(AbstractKCPManager, asyncio.DatagramProtocol):
    _accept_dict = {}

    def __init__(self, loop):
        super(KCPServerManager, self).__init__(loop, None)
        self.loop.call_later(0.03, self.interval)
        self._acceptable = asyncio.Event()

    def output(self, data, addr=None):
        print("server output")
        super(KCPServerManager, self).output(data, self.remote_addr)

    def dispatch(self, conv, data, addr):
        print("server recv data")
        if addr != self.remote_addr:
            self.remote_addr = addr
        if conv in self._conns:
            conversation = self._conns[conv]
            print("server recv in status %d" % conversation.kcp.input(data, len(data)))
            self._active_conns.add(conv)
        else:
            if conv not in self._accept_dict:
                kcp = self.create_kcp(conv, output=self.output)
                kcp.input(data, len(data))
                self._accept_dict[conv] = kcp
                if not self._acceptable.is_set():
                    self._acceptable.set()
            else:
                kcp = self._accept_dict[conv]
                kcp.input(data, len(data))

    async def start_serve(self, cb):
        while True:
            await self._acceptable.wait()
            while self._accept_dict:
                conv, kcp = self._accept_dict.popitem()
                upstream, downstream = self.create_stream()
                downstream_reader, downstream_writer = await asyncio.open_connection(sock=downstream, loop=self.loop)
                upstream_reader, upstream_writer = await asyncio.open_connection(sock=upstream, loop=self.loop)
                conversation = Conversation(conv=conv,
                                            kcp=kcp,
                                            upstream_reader=upstream_reader,
                                            upstream_writer=upstream_writer,
                                            downstream_reader=downstream_reader,
                                            downstream_writer=downstream_writer)
                self._conns[conv] = conversation
                self.loop.create_task(self.upstream_waiter(conv, downstream_reader))
                self.loop.create_task(cb(upstream_reader, upstream_writer))
                self._active_conns.add(kcp.conv)
            self._acceptable = asyncio.Event()

    def __call__(self, *args, **kwargs):
        return self
