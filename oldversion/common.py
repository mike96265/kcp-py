import asyncio
import functools
import time
from asyncio import Future, DatagramProtocol
from typing import Union, Tuple, Dict

from oldversion.KCP import KCP

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
    transport: DatagramProtocol = None
    connections: Dict[int, UKCP] = None
    recv_wait: Dict[int, Future] = None
    remote_addr: Tuple[str, int] = None
    conv: int = None

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
