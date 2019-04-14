import asyncio
import functools
from typing import Tuple
import uvloop

from KCP import KCP
from KCPClient import KCPClientController


class KCPServerController(KCPClientController):

    def datagram_received(self, data: bytearray, addr: Tuple[str, int]):
        self.client_addr = addr
        conv = KCP.ikcp_decode32u(data, 0)
        conversation = self.convs.get(conv)
        if conversation:
            self.input(conv, data)
        else:
            self.recv_buffers[conv].append(data)
            task = self.loop.create_task(self.loop.create_connection(
                functools.partial(self.stream_protocol, conv=conv), host=self.remote_addr[0], port=self.remote_addr[1]))
            task.add_done_callback(self.flush_input)

    def flush_input(self, fut):
        transport, protocol = fut.result()
        conv = protocol.conv
        buffers = self.input_buffer.get(conv)
        while buffers:
            self.input(conv, buffers.pop(0))

    def connection_lost(self, exc: Exception):
        self.transport = None

    async def start(self):
        await self.loop.create_datagram_endpoint(self.datagram_endpoint, local_addr=self.local_addr)
        self.loop.call_soon(self.interval)


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()
    server = KCPServerController(loop, local_addr=('127.0.0.1', 8888), remote_addr=('127.0.0.1', 9999))
    loop.create_task(server.start())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.close()
