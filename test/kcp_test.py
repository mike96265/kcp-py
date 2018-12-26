import time

from KCP import KCP


class LocalKCP(KCP):

    def __init__(self, conv):
        super(LocalKCP, self).__init__(conv)
        self.out_buffer = bytearray()

    def output(self, buffer, size):
        print(buffer[:size])


def current():
    return int(time.time() * 1000)


if __name__ == '__main__':
    k1 = LocalKCP(1)
    k1.update(current())
    k1.send(bytearray(b'12345'))
    while True:
        try:
            time.sleep(0.05)
            k1.update(current())
        except KeyboardInterrupt as err:
            break
