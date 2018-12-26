import asyncio
import logging
import socket
import time
from asyncio import transports, protocols
from typing import Union, Text, Tuple

from KCP import KCP
from common import StreamIO, Connection, Ready

logger = logging.getLogger(__name__)
TWELVE_HOUR = 12 * 60 * 60 * 1000


class ClientProxy:
    server = None
    connections = {}

    _conv_generator = (i for i in range(TWELVE_HOUR))

    def __init__(self, listen_host, listen_port, remote_host, remote_port, loop: asyncio.AbstractEventLoop = None):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.loop = loop or asyncio.get_event_loop()
        self.transport = None
        self.protocol = None

    async def start_listen(self, **kwargs):
        self.server = await asyncio.start_server(self.dispatcher, self.listen_host, self.listen_port, loop=self.loop,
                                                 **kwargs)
        self.transport, self.protocol = await self.loop.create_datagram_endpoint(lambda: ClientDataForwarder(self),
                                                                                 remote_addr=(
                                                                                     self.remote_host,
                                                                                     self.remote_port))
        for sock in self.server.sockets:
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                host, port, *_ = sock.getsockname()
                logger.info("serving on %s:%s", host, port)

    async def dispatcher(self, user_reader: asyncio.StreamReader, user_writer: asyncio.StreamWriter):
        host, port, *_ = user_writer.get_extra_info("peername", ("", ""))
        logger.info("new connection from %s:%s", host, port)
        stream = StreamIO(user_reader, user_writer, loop=self.loop)
        conv = self.get_conv()
        session = KCP(conv, self.transport)
        connection = Connection(
            session=session,
            stream=stream,
            loop=self.loop,
            wait_input=asyncio.Future(),
            extra_workers=set()
        )
        session.update(self.current)
        # update_interval = (session.check(self.current) - self.current) // 1000
        self.connections[conv] = connection
        pending = {
            self.read_from_client(connection),
            self.read_from_remote(connection)
        }
        try:
            while True:
                done, pending = await asyncio.wait(
                    pending | connection.extra_workers,
                    return_when=asyncio.FIRST_COMPLETED,
                    loop=self.loop
                )
                connection.extra_workers -= done
                for task in done:
                    try:
                        ready, *rest = task.result()
                        if ready is Ready.input:
                            if not rest[0]:
                                break
                            connection.wait_input = asyncio.Future()
                            connection.session.input(rest[0])
                            pending.add(self.read_from_remote(connection))
                        elif ready is Ready.send:
                            connection.wait_output = asyncio.Future()
                            pending.add(self.read_from_client(connection))
                            self.transport.write(rest[0])
                        else:
                            pass
                    except Exception as err:
                        pass
        except (asyncio.CancelledError, Exception) as err:
            logger.error(str(err))
        finally:
            connection.stream.close()

    # def open_datagram_connection(self):
    #     transport, protocol = await self.loop.create_datagram_endpoint(ClientDataForwarder,
    #     data_writer = UDPWriter(protocol, transport, (self.remote_host, self.remote_port))
    #     data_reader = UDPReader(protocol, transport, (self.remote_host, self.remote_port))
    #     return data_reader, data_writer

    @classmethod
    def get_conv(cls):
        while True:
            try:
                return next(cls._conv_generator)
            except StopIteration:
                cls._conv_generator = (i for i in range(TWELVE_HOUR))

    @classmethod
    async def read_from_client(cls, connection):
        return Ready.send, (await connection.stream.read(2))

    @classmethod
    async def read_from_remote(cls, connection):
        return Ready.input, (await connection.wait_input)

    @classmethod
    async def write_to_remote(cls, connection):
        return Ready.output, (await connection.wait_output)

    @property
    def current(self):
        return int(time.time() * 1000)

    async def interval(self, val: int):
        while True:
            await asyncio.sleep(val // 1000)
            for conn in self.connections:
                conn.session.update(self.current)
                buffer = bytes(1024)
                n = conn.session.recv(buffer)
                conn.extra_workers.add(conn.stream.write(buffer[:n]))


class ClientDataForwarder(protocols.DatagramProtocol):

    def __init__(self, proxy: ClientProxy):
        self.proxy = proxy

    def connection_made(self, transport: transports.BaseTransport):
        self.transport = transport

    def datagram_received(self, data: Union[bytes, Text], addr: Tuple[str, int]):
        conv = KCP.ikcp_decode32u(data, 0)
        connection = self.proxy.connections.get(conv, None)
        if connection is not None:
            if connection.wait_input.done():
                pre_data = connection.wait_input.result()
                connection.wait_input = asyncio.Future()
                connection.wait_input.set_result(pre_data + data)
            else:
                connection.wait_input.set_result(data)


if __name__ == '__main__':
    client = ClientProxy('127.0.0.1', 7777, '127.0.0.1', 8888)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.start_listen())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
