import asyncio

from KCP import kcp_now


class Updater:

    def __init__(self):
        self.tunnels = set()
        self.interval = 0.05
        self.raw_interval = 50
        self.register = self.tunnels.add
        self.unregister = self.tunnels.remove

    def update(self):
        for tunnel in self.tunnels:
            now = kcp_now()
            sessions = tunnel.sessions
            active = tunnel.active_sessions
            active_pop = active.pop
            active_add = active.add
            try:
                conv = active_pop()
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
            except KeyError:
                raw_interval = self.raw_interval
                for session in sessions.values():
                    if session.next_update - now < raw_interval:
                        active_add(session.conv)
        asyncio.get_event_loop().call_later(self.interval, self.update)

    def load_config(self, config):
        self.raw_interval = config.interval
        self.interval = config.interval / 1000

    def run(self):
        loop = asyncio.get_event_loop()
        loop.call_soon(self.update)


updater = Updater()
