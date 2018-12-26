import asyncio
import logging
import time
from asyncio import protocols, transports, AbstractEventLoop
from typing import Tuple, Text, Union

from common import StreamIO, Connection, Ready
from KCP import KCP

logger = logging.getLogger(__name__)


class ServerProxy:
    connections = {}

    def __init__(self, listen_host, listen_port, remote_host, remote_port, loop: AbstractEventLoop = None):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.loop = loop or asyncio.get_event_loop()
        self.transport = None
        self.protocol = None

    async def start_listen(self, **kwargs):
        self.transport, self.protocol = await self.loop.create_datagram_endpoint(lambda: ServerDataForwarder(self),
                                                                                 local_addr=(
                                                                                     self.listen_host,
                                                                                     self.listen_port))

    async def dispatcher(self, connection):
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

    @classmethod
    async def read_from_client(cls, connection):
        return Ready.send, (await connection.stream.read(2))

    @classmethod
    async def write_to_client(cls, connection, data: Union[bytes, bytearray]):
        return Ready.recv, (await connection.stream.write(data))

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


class ServerDataForwarder(protocols.DatagramProtocol):

    def __init__(self, proxy: ServerProxy):
        self.proxy = proxy

    def connection_made(self, transport: transports.BaseTransport):
        self.transport = transport

    def datagram_received(self, data: Union[bytes, Text], addr: Tuple[str, int]):
        wait_to_run = False
        conv = KCP.ikcp_decode32u(data, 0)
        connection = self.proxy.connections.get(conv, None)
        if connection is None:
            session = KCP(conv, transports)
            loop = asyncio.get_event_loop()
            reader, writer = loop.run_until_complete(
                asyncio.open_connection(self.proxy.remote_host, self.proxy.remote_port,
                                        loop=self.proxy.loop))
            stream = StreamIO(reader, writer, loop=self.proxy.loop)
            connection = Connection(
                session=session,
                stream=stream,
                loop=self.proxy.loop,
                wait_input=asyncio.Future(),
                extra_workers=set()
            )
            self.proxy.connections[conv] = connection
            wait_to_run = True
        if connection.wait_input.done():
            pre_data = connection.wait_input.result()
            connection.wait_input = asyncio.Future()
            connection.wait_input.set_result(pre_data + data)
        else:
            connection.wait_input.set_result(data)
        if wait_to_run:
            try:
                self.proxy.loop.run_until_complete(self.proxy.dispatcher(connection))
            except Exception:
                pass


if __name__ == '__main__':
    server = ServerProxy('127.0.0.1', 8888, '127.0.0.1', 9999)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server.start_listen())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
