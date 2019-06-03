import asyncio


class Protocol(asyncio.DatagramProtocol):

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data, addr) -> None:
        received = data.decode('utf8')
        print(received)
        self.transport.sendto(data, addr)


async def main():
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(Protocol, remote_addr=('192.168.1.4', 8000))
    transport.sendto('hello world!'.encode('utf8'))


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
