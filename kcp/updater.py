import asyncio

from KCP import kcp_now


class Updater:

    def __init__(self):
        self.tunnels = set()
        self.interval = 0.05
        self.raw_interval = 50

    def register(self, tunnel):
        self.tunnels.add(tunnel)

    def unregister(self, tunnel):
        self.tunnels.remove(tunnel)

    def update(self):
        now = kcp_now()
        for tunnel in self.tunnels:
            sessions = tunnel.sessions
            active = tunnel.active_sessions
            while active:
                conv = active.pop()
                session = sessions[conv]
                kcp = session.kcp
                kcp.update(now)
                if kcp.state == -1:
                    tunnel.close_session(session)
                else:
                    peeksize = kcp.peeksize()
                    if peeksize != 0 and peeksize != -1:
                        data = bytes(peeksize)
                        kcp.recv(data, peeksize)
                        session.protocol.data_received(data)
                    next_call = kcp.check(now)
                    session.next_update = next_call
            for session in sessions.values():
                if session.next_update - now < self.raw_interval:
                    active.add(session.conv)
        asyncio.get_event_loop().call_later(self.interval, self.update)

    def load_config(self, config):
        self.raw_interval = config.interval
        self.interval = config.interval / 1000

    def run(self):
        loop = asyncio.get_event_loop()
        loop.call_soon(self.update)


updater = Updater()
