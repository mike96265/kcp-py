import asyncio
import time
from asyncio import protocols, transports, AbstractEventLoop, Future, DatagramProtocol
import collections
import functools
from enum import Enum
from typing import Union, Tuple, Text, Dict

from KCP import KCP

TWELVE_HOUR = 12 * 60 * 60 * 1000


def current():
    return int(time.time() * 1000)


class UKCP(KCP):

    def __init__(self, conv, manager: 'AbstractManager'):
        super(UKCP, self).__init__(conv)
        self.manager = manager

    def output(self, buffer: bytearray, size):
        self.manager.output(buffer[:size])

    def __lt__(self, other: 'UKCP'):
        _current = current()
        return self.check(_current) < other.check(_current)

    def __eq__(self, other: 'UKCP'):
        _current = current()
        return self.check(_current) == other.check(_current)

    def __gt__(self, other: 'UKCP'):
        _current = current()
        return self.check(_current) > other.check(_current)


class AbstractManager:
    transport: DatagramProtocol
    connections: Dict[int:UKCP]
    recv_wait: Dict[int: Future]
    remote_addr: Tuple[str, int]
    conv: int

    def output(self, buffer):
        self.transport.sendto(buffer, addr=self.remote_addr)

    def input(self, conv: int, data: Union[bytearray, bytes] = None):
        kcp = self.connections.get(conv)
        kcp.input(data)

    async def recv(self, kcp):
        data = await self.recv_wait[kcp.conv]
        self.recv_wait[kcp.conv] = Future()
        return 'recv', data

    def send(self, kcp, data):
        kcp.send(data)

    async def interval(self):
        while True:
            await asyncio.sleep(0.1)
            for i in self.connections.values():
                i.update(current())
                data = i.recv()
                if data != -2 and data:
                    if self.recv_wait[i.conv].done():
                        self.recv_wait[i.conv].result()[-1:] = data
                    else:
                        self.recv_wait[i.conv].set_result(data)

    def get_session(self, conv=None):
        if conv is not None:
            conv = conv
        else:
            conv = self.conv
        kcp = UKCP(conv, self)
        kcp.update(current())
        self.connections[conv] = kcp
        return kcp


def _with_timeout(name):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(cls, *args, **kwargs):
            coro = f(cls, *args, **kwargs)
            timeout = getattr(cls, name)
            return asyncio.wait_for(coro, timeout, loop=cls.loop)

        return wrapper

    return decorator


def with_timeout(name):
    """
    Method decorator, wraps method with :py:func:`asyncio.wait_for`. `timeout`
    argument takes from `name` decorator argument or "timeout".

    :param name: name of timeout attribute
    :type name: :py:class:`str`

    :raises asyncio.TimeoutError: if coroutine does not finished in timeout

    Wait for `self.timeout`
    ::

        >>> def __init__(self, ...):
        ...
        ...     self.timeout = 1
        ...
        ... @with_timeout
        ... async def foo(self, ...):
        ...
        ...     pass

    Wait for custom timeout
    ::

        >>> def __init__(self, ...):
        ...
        ...     self.foo_timeout = 1
        ...
        ... @with_timeout("foo_timeout")
        ... async def foo(self, ...):
        ...
        ...     pass

    """

    if isinstance(name, str):
        return _with_timeout(name)
    else:
        return _with_timeout("timeout")(name)


class Ready(Enum):
    send = "send"
    input = "input"
    interval = "interval"
    check = "check"


class Connection(collections.defaultdict):
    """
    Connection state container for transparent work with futures for async
    wait

    :param loop: event loop
    :type loop: :py:class:`asyncio.BaseEventLoop`

    :param kwargs: initialization parameters

    Container based on :py:class:`collections.defaultdict`, which holds
    :py:class:`asyncio.Future` as default factory. There is two layers of
    abstraction:

    * Low level based on simple dictionary keys to attributes mapping and
        available at Connection.future.
    * High level based on futures result and dictionary keys to attributes
        mapping and available at Connection.

    To clarify, here is groups of equal expressions
    ::

        >>> connection.future.foo
        >>> connection["foo"]

        >>> connection.foo
        >>> connection["foo"].result()

        >>> del connection.future.foo
        >>> del connection.foo
        >>> del connection["foo"]
    """

    __slots__ = ("future",)

    class Container:

        def __init__(self, storage):
            self.storage = storage

        def __getattr__(self, name):
            return self.storage[name]

        def __delattr__(self, name):
            self.storage.pop(name)

    def __init__(self, *, loop=None, **kwargs):
        super().__init__(functools.partial(asyncio.Future, loop=loop))
        self.future = Connection.Container(self)
        self["loop"].set_result(loop or asyncio.get_event_loop())
        for k, v in kwargs.items():
            self[k].set_result(v)

    def __getattr__(self, name):
        if name in self:
            return self[name].result()
        else:
            raise AttributeError("'{}' not in storage".format(name))

    def __setattr__(self, name, value):
        if name in Connection.__slots__:
            super().__setattr__(name, value)
        else:
            if self[name].done():
                self[name] = super().default_factory()
            self[name].set_result(value)

    def __delattr__(self, name):
        if name in self:
            self.pop(name)


class UDPWriter:

    def __init__(self, protocol: protocols.BaseProtocol, transport: transports.BaseTransport, remote_addr):
        self.protocol = protocol
        self.transport = transport
        self.remote_addr = remote_addr

    def write(self, data):
        self.transport.sendto(data, self.remote_addr)

    async def drain(self):
        """do nothing"""

    async def close(self):
        self.transport.close()


class UDPReader:

    def __init__(self, protocol: protocols.BaseProtocol, transport: transports.BaseTransport, remote_addr):
        self.protocol = protocol
        self.transport = transport
        self.remote_addr = remote_addr

    async def read(self, count=-1):
        return await self.protocol.read(count)


class AbstractStreamIO:

    async def read(self, count=-1):
        raise NotImplementedError

    async def write(self, data):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


class StreamIO(AbstractStreamIO):

    def __init__(self, reader: Union[asyncio.StreamReader, UDPReader], writer: Union[asyncio.StreamWriter, UDPWriter],
                 *, timeout: int = None, read_timeout: int = None, write_timeout: int = None, loop=None):
        self.reader = reader
        self.writer = writer
        self.read_timeout = read_timeout or timeout
        self.write_timeout = write_timeout or timeout
        self.loop = loop or asyncio.get_event_loop()

    # @with_timeout("read_timeout")
    async def read(self, count=-1):
        return await self.reader.read(count)

    # @with_timeout("write_timeout")
    async def write(self, data):
        self.writer.write(data)
        return await self.writer.drain()

    def close(self):
        self.writer.close()


class KCPWithUDP(KCP):

    def __init__(self, conv, transport):
        super(KCPWithUDP, self).__init__(conv)
        self.transport = transport

    def output(self, buffer: bytearray, size):
        self.transport.sendto(buffer[:size])


class UKCP(KCP):
    connections = {}

    def __init__(self, conv):
        super(KCP, self).__init__(conv)
        self.connections[conv] = self
        self._wait_input = asyncio.Future()

    def output(self, buffer, size):
        self.transport.sendto(buffer[:size])

    @classmethod
    async def start(cls, local_addr: Tuple[str, int] = None, remote_addr: Tuple[str, int] = None,
                    loop: AbstractEventLoop = None):
        if all([local_addr, remote_addr]):
            raise ValueError("remote_addr and local_addr can't be set at the same time")
        elif remote_addr:
            cls.transport, cls.protocol = await loop.create_datagram_endpoint(UKCPClientManager,
                                                                              remote_addr=remote_addr)
        elif local_addr:
            cls.transport, cls.protocol = await loop.create_datagram_endpoint(UKCPServerManager,
                                                                              local_addr=local_addr)
        else:
            raise ValueError("u have to set either local_addr to listen or remote_addr to connect")

    async def read_from_remote(self):
        data = (await self._wait_input)
        self._wait_input = asyncio.Future()
        return Ready.input, data


class UKCPClientManager(protocols.DatagramProtocol):

    def __init__(self, cls: UKCP):
        self.cls = cls

    def connection_made(self, transport: transports.BaseTransport):
        self.transport = transport

    def datagram_received(self, data: Union[bytes, Text], addr: Tuple[str, int]):
        conv = KCP.ikcp_decode32u(bytearray(data), 0)
        if conv not in self.cls.connections:
            pass


class UKCPServerManager(protocols.DatagramProtocol):

    def __init__(self, cls):
        self.cls = cls

    def connection_made(self, transport: transports.BaseTransport):
        pass
