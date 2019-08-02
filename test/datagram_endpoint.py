import asyncio
from asyncio import protocols, transports


class DataGramConnProtocol(protocols.DatagramProtocol):

    def connection_made(self, transport: transports.DatagramTransport) -> None:
        print("conn established local_addr: {} remote_addr: {}".format(
            transport.get_extra_info('sockname'),
            transport.get_extra_info('peername')
        ))
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        print(f"conn received data from {addr}")
        self.transport.sendto(data)


class DataGramServerProtocol(protocols.DatagramProtocol):
    connections = set()

    def connection_made(self, transport: transports.DatagramTransport) -> None:
        print("server start listen")
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        print(f"server received data from {addr}")
        print(f'addr {"in" if addr in self.connections else "not in"} self connections')
        self.connections.add(addr)
        loop = asyncio.get_event_loop()
        task = loop.create_task(loop.create_datagram_endpoint(
            DataGramConnProtocol,
            local_addr=self.transport.get_extra_info('sockname'),
            remote_addr=addr,
            reuse_address=True
        ))

        def client_connected_cb(result: asyncio.Future):
            if not result.exception():
                transport, protocol = result.result()
                protocol.datagram_received(data, addr)
            else:
                print(result.exception())

        task.add_done_callback(client_connected_cb)

    def connection_lost(self, exc) -> None:
        pass

    def error_received(self, exc: Exception) -> None:
        pass


async def main():
    loop = asyncio.get_event_loop()
    await loop.create_datagram_endpoint(
        DataGramServerProtocol,
        local_addr=('127.0.0.1', 1234),
        reuse_address=True
    )
    fin = asyncio.Event()
    await fin.wait()


if __name__ == '__main__':
    asyncio.run(main())
