import asyncio
from asyncio import protocols


class UdpProtocol(protocols.DatagramProtocol):

    def connection_made(self, transport):
        self.transport = transport
        print(self.transport._extra.items())

    def datagram_received(self, data, addr) -> None:
        self.transport.sendto(data, addr)

    def connection_lost(self, exc):
        pass


async def main():
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(UdpProtocol, local_addr=('127.0.0.1', 9999))
    await asyncio.sleep(100)


if __name__ == '__main__':
    asyncio.run(main())
