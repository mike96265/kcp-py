import time

from KCP import KCP


class NKCP(KCP):

    def __init__(self, conv):
        super(NKCP, self).__init__(conv)

    def set_k(self, k):
        self.k = k

    def output(self, buffer, size):
        self.k.input(buffer[:size])


def current():
    return int(time.time() * 1000)


if __name__ == '__main__':
    k1 = NKCP(1)
    k2 = NKCP(1)
    k1.set_k(k2)
    k2.set_k(k1)
    k1.update(current())
    k2.update(current())
    a = bytearray(10)
    for i in range(5):
        k1.send(bytearray(b'12345'))
        for x in range(3):
            time.sleep(0.05)
            k1.update(current())
            k2.update(current())
        n = k2.recv(a)
        print([int(y) for y in a[:n]])
    for i in range(5):
        k2.send(bytearray(b'12345'))
        for x in range(3):
            time.sleep(0.05)
            k2.update(current())
            k1.update(current())
        n = k1.recv(a)
        print([int(y) for y in a[:n]])
