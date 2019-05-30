import asyncio
import functools
import logging
import traceback
from collections import namedtuple, defaultdict
from typing import Dict, Tuple, Optional
import uvloop

from oldversion.KCP import KCP

logger = logging.getLogger("KCP")

TWELVE_HOUR = 12 * 60 * 60 * 1000


class UKCPSession(KCP):
    def __init__(self, conv, controller):
        super(UKCPSession, self).__init__(conv)
        self.controller = controller

    def output(self, buffer, size):
        self.controller.output(self.conv, buffer[:size])


class Connection(asyncio.Protocol):

    def __init__(self, conv: int, controller: 'KCPClientController'):
        self.conv = conv
        self.controller = controller
        self.transport = None
        self.ready = asyncio.Future()

    def connection_made(self, transport: asyncio.Transport) -> None:
        logger.info(f"""stream established sockname: {transport.get_extra_info(
            'sockname')} <-> peername: {transport.get_extra_info('peername')}""")
        self.transport = transport
        self.ready.set_result(-1)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self.controller.close_conversation(self.conv)

    def data_received(self, data: bytearray) -> None:
        self.controller.send(self.conv, data)

    def pause_writing(self) -> None:
        self.ready = asyncio.Future()
        self.ready.add_done_callback(self.controller.flush_recv)

    def resume_writing(self) -> None:
        self.ready.set_result(self.conv)


Conversation = namedtuple('Conversation', ('connection', 'session'))


class KCPClientController(asyncio.DatagramProtocol):
    protocol = Connection

    def __init__(self, loop: asyncio.AbstractEventLoop, remote_addr, local_addr):
        self.loop = loop
        self.remote_addr = remote_addr
        self.local_addr = local_addr
        self.convs: Dict[int, Conversation] = {}
        self.active_conns = set()
        self._conv_generator = (i for i in range(TWELVE_HOUR))
        self.output_buffers = defaultdict(list)
        self.recv_buffers = defaultdict(list)
        self.input_buffer = defaultdict(list)
        self.transport = None
        self.update_schedule: Dict[int: asyncio.Task] = {}
        self.client_addr = None

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport

    def datagram_received(self, data: bytearray, addr: Tuple[str, int]):
        conv = KCP.ikcp_decode32u(data, 0)
        conversation = self.convs.get(conv)
        if conversation:
            self.input(conv, data)

    def connection_lost(self, exc: Exception):
        logger.error('connection lost, trying to reconnect')
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        self.transport = None
        task = self.loop.create_task(
            self.loop.create_datagram_endpoint(self.datagram_endpoint, remote_addr=('127.0.0.1', 8888)))
        task.add_done_callback(self.flush_output)

    def create_session(self, conv):
        session = UKCPSession(conv, self)
        session.set_nodelay(1, 10, 2, 1)
        return session

    def generate_conv(self):
        try:
            conv = next(self._conv_generator)
        except StopIteration:
            self._conv_generator = (i for i in range(TWELVE_HOUR))
            conv = next(self._conv_generator)
        return conv

    '''data proxy and data buffer'''

    def output(self, conv, buffer: bytearray):
        if self.transport is None:
            self.output_buffers[conv].append(buffer)
        else:
            self.transport.sendto(buffer, getattr(self, 'client_addr'))

    def flush_output(self, fut):
        for conv in self.output_buffers:
            self._flush_output(conv)

    def _flush_output(self, conv):
        buffers = self.output_buffers.get(conv)
        while buffers:
            self.output(conv, buffers.pop(0))
        del self.output_buffers[conv]

    def input(self, conv, data):
        self.active_conns.add(conv)
        if conv in self.update_schedule and not self.update_schedule[conv].cancelled():
            self.update_schedule[conv].cancel()
            del self.update_schedule[conv]
        self.convs[conv].session.input(data)

    def send(self, conv, data: bytearray):
        self.active_conns.add(conv)
        if conv in self.update_schedule and not self.update_schedule[conv].cancelled():
            self.update_schedule[conv].cancel()
            del self.update_schedule[conv]
        self.convs[conv].session.send(data)

    def recv(self, conv, data: bytearray):
        connection = self.convs[conv].connection
        if connection.ready.done():
            connection.transport.write(data)
        else:
            self.recv_buffers[conv].append(data)

    def flush_recv(self, fut):
        conv = fut.result()
        if conv != -1:
            self._flush_recv(conv)
        else:
            for conv in self.recv_buffers:
                self._flush_recv(conv)

    def _flush_recv(self, conv):
        connection = self.convs[conv].connection
        buffers = self.recv_buffers.get(conv)
        while buffers:
            connection.transport.write(buffers.pop(0))
        del self.recv_buffers[conv]

    '''interval management'''

    def interval(self):
        while self.active_conns:
            conv = self.active_conns.pop()
            self.update(conv)
        self.loop.call_later(0.01, self.interval)

    def update(self, conv):
        current = int(self.loop.time() * 1000)
        conversion = self.convs[conv]
        session = conversion.session
        session.update(current)
        if session.state == -1:
            self.close_conversation(conv)
        peeksize = session.peeksize()
        if peeksize not in (0, -1):
            data = session.recv(peeksize)
            self.recv(conv, data)
        next_call = session.check(current)
        schedule = self.loop.call_at(next_call / 1000, functools.partial(self.update, conv))
        self.update_schedule[conv] = schedule

    ''' switch protocol'''

    def datagram_endpoint(self):
        return self

    def stream_protocol(self, conv=-1):
        if conv == -1:
            conv = self.generate_conv()
        session = self.create_session(conv)
        conn = self.protocol(conv, self)
        self.convs[conv] = Conversation(connection=conn, session=session)
        self.active_conns.add(conv)
        return conn

    def close_conversation(self, conv):
        if conv in self.output_buffers:
            del self.output_buffers[conv]
        if conv in self.recv_buffers:
            del self.recv_buffers[conv]
        if conv in self.update_schedule:
            task = self.update_schedule[conv]
            if not task.cancelled():
                self.update_schedule[conv].cancel()
            del self.update_schedule[conv]
        if conv in self.active_conns:
            self.active_conns.remove(conv)
        self.convs[conv].connection.transport.close()
        del self.convs[conv]

    async def start(self):
        await self.loop.create_datagram_endpoint(self.datagram_endpoint, remote_addr=self.remote_addr)
        await self.loop.create_server(self.stream_protocol, host=self.local_addr[0], port=self.local_addr[1])
        self.loop.call_soon(self.interval)


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()
    client = KCPClientController(loop, local_addr=('127.0.0.1', 7777), remote_addr=('yukityan.cc', 29900))
    loop.create_task(client.start())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.close()
