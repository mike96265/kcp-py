import asyncio


class EchoServerProtocol:
    def connection_made(self, transport):
        self.transport = transport
        print("connection made in server")

    def datagram_received(self, data, addr):
        message = data.decode()
        print('Received %r from %s' % (message, addr))
        print('Send %r to %s' % (message, addr))
        self.transport.sendto(data, addr)

    def connection_lost(self, exc):
        print("Connection closed on server")


class EchoClientProtocol:
    def __init__(self, message, loop):
        self.message = message
        self.loop = loop
        self.transport = None
        self.on_con_lost = loop.create_future()

    def connection_made(self, transport):
        self.transport = transport
        print('Send:', self.message)
        self.transport.sendto(self.message.encode())

    def datagram_received(self, data, addr):
        print("Received:", data.decode())

        print("Closing the socket on client")
        self.transport.close()

    def error_received(self, exc):
        print('Error received:', exc)

    def connection_lost(self, exc):
        print("Connection closed on client")
        self.on_con_lost.set_result(True)


async def main():
    print("Starting UDP server")

    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    loop = asyncio.get_running_loop()

    # One protocol instance will be created to serve all
    # client requests.
    server_transport, server_protocol = await loop.create_datagram_endpoint(
        lambda: EchoServerProtocol(),
        local_addr=('127.0.0.1', 9999))

    message = "Hello World!"
    client_transport1, client_protocol1 = await loop.create_datagram_endpoint(
        lambda: EchoClientProtocol(message, loop),
        remote_addr=('127.0.0.1', 9999))
    client_transport2, client_protocol2 = await loop.create_datagram_endpoint(
        lambda: EchoClientProtocol(message, loop),
        remote_addr=('127.0.0.1', 9999))

    try:
        await asyncio.sleep(3)  # Serve for 1 hour.
        await client_protocol1.on_con_lost
        await client_protocol2.on_con_lost

    finally:
        server_transport.close()
        client_transport1.close()
        client_transport2.close()


if __name__ == '__main__':
    asyncio.run(main())
