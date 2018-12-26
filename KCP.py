from typing import List, Union

IKCP_RTO_NDL = 30  # no delay min rto
IKCP_RTO_MIN = 100  # normal min rto
IKCP_RTO_DEF = 200
IKCP_RTO_MAX = 60000
IKCP_CMD_PUSH = 81  # cmd: push data
IKCP_CMD_ACK = 82  # cmd: ack
IKCP_CMD_WASK = 83  # cmd: window probe (ask)
IKCP_CMD_WINS = 84  # cmd: window size (tell)
IKCP_ASK_SEND = 1  # need to send IKCP_CMD_WASK
IKCP_ASK_TELL = 2  # need to send IKCP_CMD_WINS
IKCP_WND_SND = 32
IKCP_WND_RCV = 32
IKCP_MTU_DEF = 1400
IKCP_ACK_FAST = 3
IKCP_INTERVAL = 100
IKCP_OVERHEAD = 24
IKCP_DEADLINK = 10
IKCP_THRESH_INIT = 2
IKCP_THRESH_MIN = 2
IKCP_PROBE_INIT = 7000  # 7 secs to probe window size
IKCP_PROBE_LIMIT = 120000  # up to 120 secs to probe window


class Segment:
    # session attribute

    conv = 0
    cmd = 0
    frg = 0
    wnd = 0
    ts = 0
    sn = 0
    una = 0
    resendts = 0
    rto = 0
    fastack = 0
    xmit = 0
    data: bytearray = None

    def __init__(self, size):
        self.data = bytearray(size)

    def encode(self, ptr: bytearray, offset: int):
        _offset = offset

        KCP.ikcp_encode32u(ptr, offset, self.conv)
        offset += 4
        KCP.ikcp_encode8u(ptr, offset, self.cmd)
        offset += 1
        KCP.ikcp_encode8u(ptr, offset, self.frg)
        offset += 1
        KCP.ikcp_encode16u(ptr, offset, self.wnd)
        offset += 2
        KCP.ikcp_encode32u(ptr, offset, self.ts)
        offset += 4
        KCP.ikcp_encode32u(ptr, offset, self.sn)
        offset += 4
        KCP.ikcp_encode32u(ptr, offset, self.una)
        offset += 4
        KCP.ikcp_encode32u(ptr, offset, len(self.data))
        offset += 4

        return offset - _offset


class KCP:
    # public session attribute

    # static method

    @staticmethod
    def ikcp_encode8u(p: Union[bytes, bytearray], offset: int, c: int):
        p[0 + offset] = c & 255

    @staticmethod
    def ikcp_decode8u(p: Union[bytes, bytearray], offset: int):
        return p[0 + offset]

    @staticmethod
    def ikcp_encode16u(p: Union[bytes, bytearray], offset: int, w: int):
        p[offset + 0] = (w >> 8) & 255
        p[offset + 1] = (w >> 0) & 255

    @staticmethod
    def ikcp_decode16u(p: Union[bytes, bytearray], offset: int):
        return (p[0 + offset] & 0xff) << 8 | (p[1 + offset] & 0xff)

    @staticmethod
    def ikcp_encode32u(p: Union[bytes, bytearray], offset: int, l: int):
        p[offset + 0] = (l >> 24) & 255
        p[offset + 1] = (l >> 16) & 255
        p[offset + 2] = (l >> 8) & 255
        p[offset + 3] = (l >> 0) & 255

    @staticmethod
    def ikcp_decode32u(p: Union[bytes, bytearray], offset: int):
        return (p[offset + 0] & 0xff) << 24 \
               | (p[offset + 1] & 0xff) << 16 \
               | (p[offset + 2] & 0xff) << 8 \
               | p[offset + 3] & 0xff

    @staticmethod
    def _ibound(lower: int, middle: int, upper: int):
        return min(max(lower, middle), upper)

    @staticmethod
    def _itimediff(later: int, earlier: int):
        return later - earlier

    conv = 0
    # user = user
    snd_una = 0
    snd_nxt = 0
    rcv_nxt = 0
    ts_recent = 0
    ts_lastack = 0
    ts_probe = 0
    probe_wait = 0
    snd_wnd = IKCP_WND_SND
    rcv_wnd = IKCP_WND_RCV
    rmt_wnd = IKCP_WND_RCV
    cwnd = 0
    incr = 0
    probe = 0
    mtu = IKCP_MTU_DEF
    mss = mtu - IKCP_OVERHEAD

    state = 0
    # long ackblock = 0
    # long ackcount = 0
    rx_srtt = 0
    rx_rttval = 0
    rx_rto = IKCP_RTO_DEF
    rx_minrto = IKCP_RTO_MIN
    current = 0
    interval = IKCP_INTERVAL
    ts_flush = IKCP_INTERVAL
    nodelay = 0
    updated = 0
    logmask = 0
    ssthresh = IKCP_THRESH_INIT
    fastresend = 0
    nocwnd = 0
    xmit = 0
    dead_link = IKCP_DEADLINK

    # long output = NULL
    # long writelog = NULL

    def __init__(self, conv):
        self.conv = conv
        self.buffer = bytearray((self.mtu + IKCP_OVERHEAD) * 3)
        self.nrcv_buf: List[Segment] = list()
        self.nsnd_buf: List[Segment] = list()
        self.nrcv_que: List[Segment] = list()
        self.nsnd_que: List[Segment] = list()
        self.acklist = list()
        # self.transport = transport
        # self.output_buffer = output_buffer

    def recv(self):
        """
        Put user data out self.nrcv_que in buffer.
        """

        # there is no available segment in nrcv_que
        buffer = bytearray()

        # if not len(self.nrcv_que):
        #     return -1

        peeksize = self.peeksize()

        if peeksize < 0:
            return -2
        # if peeksize > len(buffer):
        #     return -3

        recover = False

        if len(self.nrcv_que) >= self.rcv_wnd:
            recover = True

        # merge fragment
        count = 0
        n = 0
        for segment in self.nrcv_que:
            segment_len = len(segment.data)
            buffer[n: n + segment_len] = segment.data[:]
            n += segment_len
            count += 1
            if segment.frg == 0:
                break

        if count > 0:
            self.nrcv_que[:] = self.nrcv_que[count:]

        # move available data from nrcv_buf -> nrcv_que
        count = 0
        for segment in self.nrcv_buf:
            if (segment.sn == self.rcv_nxt) and (len(self.nrcv_que) < self.rcv_wnd):
                self.nrcv_que.append(segment)
                self.rcv_nxt += 1
                count += 1
            else:
                break

        if count > 0:
            self.nrcv_buf[:] = self.nrcv_buf[count:]

        # fast recover
        if (len(self.nrcv_que) < self.rcv_wnd) and recover:
            # ready to send back IKCP_CMD_WINS in ikcp_flush
            # tell remote my window size
            self.probe |= IKCP_ASK_TELL
        return buffer

    def peeksize(self) -> int:
        """
        check the size of next message in the recv queue
        """
        if 0 == len(self.nrcv_que):
            return -1
        first = self.nrcv_que[0]
        if first.frg == 0:
            return len(first.data)
        if len(self.nrcv_que) < (first.frg + 1):
            return -1
        length = 0
        for segment in self.nrcv_que:
            length += len(segment.data)
            if segment.frg == 0:
                break
        return length

    def send(self, buffer: bytearray):
        """
        put user data into send queue
        """
        if 0 == len(buffer):
            return -1
        # split by mss
        if len(buffer) < self.mss:
            count = 1
        else:
            count = (len(buffer) + self.mss - 1) // self.mss

        if count > 255:
            return -2

        if count == 0:
            count = 1

        offset = 0
        length = len(buffer)

        # 分片后加入到发送队列
        for i in range(count):
            size = self.mss if (length > self.mss) else length
            segment = Segment(size)
            segment.data[:] = buffer[offset: offset + size]
            offset += size
            segment.frg = count - i - 1
            self.nsnd_que.append(segment)
            length -= size
        return 0

    def update_ack(self, rtt: int):
        """parse ack"""
        if self.rx_srtt == 0:
            self.rx_srtt = rtt
            self.rx_rttval = rtt // 2
        else:
            delta = rtt - self.rx_srtt
            if delta < 0:
                delta = -delta
            self.rx_rttval = (3 * self.rx_rttval + delta) // 4
            self.rx_srtt = (7 * self.rx_srtt + rtt) // 8
            if self.rx_srtt < 1:
                self.rx_srtt = 1
        rto = self.rx_srtt + max(1, 4 * self.rx_rttval)
        self.rx_rto = self._ibound(self.rx_minrto, rto, IKCP_RTO_MAX)

    def shrink_buf(self):
        """计算本地真实snd_una"""
        if len(self.nsnd_buf) > 0:
            self.snd_una = self.nsnd_buf[0].sn
        else:
            self.snd_una = self.snd_nxt

    def parse_ack(self, sn: int):
        """对端返回的ack，确认发送成功时，对应包从发送缓存中移除"""
        if (self._itimediff(sn, self.snd_una) < 0) or (self._itimediff(sn, self.snd_nxt) >= 0):
            return
        index = 0
        for segment in self.nsnd_buf:
            if self._itimediff(sn, segment.sn) < 0:
                break
            segment.fastack += 1
            if sn == segment.sn:
                self.nsnd_buf.pop(index)
                break
            index += 1

    def parse_una(self, una: int):
        """通过对端传回的una将已经确认发送成功的包从发送缓存中移除"""
        count = 0
        for segment in self.nsnd_buf:
            if self._itimediff(una, segment.sn) > 0:
                count += 1
            else:
                break
        if count > 0:
            self.nsnd_buf = self.nsnd_buf[count:]

    def ack_push(self, sn: int, ts: int):
        """收到数据包之后，将对应ack返回，flush时发送"""
        self.acklist.append(sn)
        self.acklist.append(ts)

    def parse_data(self, new_segment: Segment):
        """用户数据包解析"""
        sn = new_segment.sn
        repeat = False
        if (self._itimediff(sn, self.rcv_nxt + self.rcv_wnd) >= 0) or (self._itimediff(sn, self.rcv_nxt) < 0):
            return
        n = len(self.nrcv_buf) - 1
        after_idx = -1

        # 判断是否重复包，同时计算插入位置
        for i in range(n, -1, -1):
            segment = self.nrcv_buf[i]
            if segment.sn == sn:
                repeat = True
                break
            if self._itimediff(sn, segment.sn) > 0:
                after_idx = i
                break

        if not repeat:
            self.nrcv_buf.insert(after_idx + 1, new_segment)

        # 将连续包加入到接受队列
        count = 0
        for segment in self.nrcv_buf:
            if (segment.sn == self.rcv_nxt) and (len(self.nrcv_que) < self.rcv_wnd):
                self.nrcv_que.append(segment)
                self.rcv_nxt += 1
                count += 1
            else:
                break

        # 从接受缓存中移除
        if count > 0:
            self.nrcv_buf = self.nrcv_buf[count:]

    def input(self, data: bytearray):
        s_una = self.snd_una
        if len(data) < IKCP_OVERHEAD:
            return 0
        offset = 0
        while True:
            if (len(data) - offset) < IKCP_OVERHEAD:
                break
            conv = self.ikcp_decode32u(data, offset)
            offset += 4
            if self.conv != conv:
                return -1
            cmd = self.ikcp_decode8u(data, offset)
            offset += 1
            frg = self.ikcp_decode8u(data, offset)
            offset += 1
            wnd = self.ikcp_decode16u(data, offset)
            offset += 2
            ts = self.ikcp_decode32u(data, offset)
            offset += 4
            sn = self.ikcp_decode32u(data, offset)
            offset += 4
            una = self.ikcp_decode32u(data, offset)
            offset += 4
            length = self.ikcp_decode32u(data, offset)
            offset += 4

            if (len(data) - offset) < length:
                return -2

            if (
                    cmd != IKCP_CMD_PUSH
                    and cmd != IKCP_CMD_ACK
                    and cmd != IKCP_CMD_WASK
                    and cmd != IKCP_CMD_WINS
            ):
                return -3

            self.rmt_wnd = wnd
            self.parse_una(una)
            self.shrink_buf()

            if IKCP_CMD_ACK == cmd:
                if self._itimediff(self.current, ts) >= 0:
                    self.update_ack(self._itimediff(self.current, ts))
                self.parse_ack(sn)
                self.shrink_buf()
            elif IKCP_CMD_PUSH == cmd:
                if self._itimediff(sn, self.rcv_nxt + self.rcv_wnd) < 0:
                    self.ack_push(sn, ts)
                    if self._itimediff(sn, self.rcv_nxt) >= 0:
                        segment = Segment(length)
                        segment.conv = conv
                        segment.cmd = cmd
                        segment.frg = frg
                        segment.wnd = wnd
                        segment.ts = ts
                        segment.sn = sn
                        segment.una = una
                        if length > 0:
                            segment.data[:] = data[offset:offset + length]
                        self.parse_data(segment)
            elif IKCP_CMD_WASK == cmd:
                self.probe |= IKCP_ASK_TELL
            elif IKCP_CMD_WINS == cmd:
                pass
            else:
                return -3
            offset += length
        if self._itimediff(self.snd_una, s_una) > 0:
            if self.cwnd < self.rmt_wnd:
                mss = self.mss
                if self.cwnd < self.ssthresh:
                    self.cwnd += 1
                    self.incr += mss
                else:
                    if self.incr < mss:
                        self.incr = mss
                    self.incr += (mss * mss) // self.incr + (mss // 16)
                    if (self.cwnd + 1) * mss <= self.incr:
                        self.cwnd += 1
                    if self.cwnd > self.rmt_wnd:
                        self.cwnd = self.rmt_wnd
                        self.incr = self.rmt_wnd * mss
        return 0

    def wnd_unused(self):
        if len(self.nrcv_que) < self.rcv_wnd:
            return self.rcv_wnd - len(self.nrcv_que)
        return 0

    def flush(self):
        current = self.current
        change = 0
        lost = 0

        if self.updated == 0:
            return

        seg = Segment(0)
        seg.conv = self.conv
        seg.cmd = IKCP_CMD_ACK
        seg.wnd = self.wnd_unused()
        seg.una = self.rcv_nxt

        count = len(self.acklist) // 2
        offset = 0
        for i in range(count):
            if (offset + IKCP_OVERHEAD) > self.mtu:
                self.output(self.buffer, offset)
                offset = 0
            seg.sn = self.acklist[i * 2]
            seg.ts = self.acklist[i * 2 + 1]
            offset += seg.encode(self.buffer, offset)
        self.acklist.clear()

        # 判断是否需要请求对端接受窗口
        if 0 == self.rmt_wnd:
            if 0 == self.probe_wait:
                self.probe_wait = IKCP_PROBE_INIT
                self.ts_probe = self.current + self.probe_wait
            else:
                # 逐步扩大请求时间间隔
                if self._itimediff(self.current, self.ts_probe) >= 0:
                    if self.probe_wait < IKCP_PROBE_INIT:
                        self.probe_wait = IKCP_PROBE_INIT

                    self.probe_wait += self.probe_wait // 2
                    if self.probe_wait > IKCP_PROBE_LIMIT:
                        self.probe_wait = IKCP_PROBE_LIMIT
                    self.ts_probe = self.current + self.probe_wait
                    self.probe |= IKCP_ASK_SEND
        else:
            self.ts_probe = 0
            self.probe_wait = 0

        # 请求对端接受窗口
        if (self.probe & IKCP_ASK_SEND) != 0:
            seg.cmd = IKCP_CMD_WASK
            if (offset + IKCP_OVERHEAD) > self.mtu:
                self.output(self.buffer, offset)
                offset = 0
            offset += seg.encode(self.buffer, offset)

        # 告诉对端自己的接受窗口
        if (self.probe & IKCP_ASK_TELL) != 0:
            seg.cmd = IKCP_CMD_WINS
            if (offset + IKCP_OVERHEAD) > self.mtu:
                self.output(self.buffer, offset)
                offset = 0
            offset += seg.encode(self.buffer, offset)

        self.probe = 0

        # 计算 window size
        cwnd = min(self.snd_wnd, self.rmt_wnd)

        # 如果采用拥塞控制
        if self.nocwnd == 0:
            cwnd = min(self.cwnd, cwnd)

        count = 0

        # move data from snd_queue to snd_buf

        for nsnd_que_item in self.nsnd_que:
            if (self._itimediff(self.snd_nxt, self.snd_una + cwnd)) >= 0:
                break

            new_segment = nsnd_que_item
            new_segment.conv = self.conv
            new_segment.cmd = IKCP_CMD_PUSH
            new_segment.wnd = seg.wnd
            new_segment.ts = current
            new_segment.sn = self.snd_nxt
            new_segment.una = self.rcv_nxt
            new_segment.resendts = current
            new_segment.rto = self.rx_rto
            new_segment.fastack = 0
            new_segment.xmit = 0
            self.nsnd_buf.append(new_segment)
            self.snd_nxt += 1
            count += 1

        if count > 0:
            self.nsnd_que = self.nsnd_que[count:]

        # calculate resent
        resent = self.fastresend if (self.fastresend > 0) else 0xffffffff
        rtomin = (self.rx_rto >> 3) if (self.nodelay == 0) else 0

        # flush data segment
        for segment in self.nsnd_buf:
            need_send = False
            if segment.xmit == 0:
                # 第一次传输
                need_send = True
                segment.xmit += 1
                segment.rto = self.rx_rto
                segment.resendts = current + segment.rto + rtomin
            elif self._itimediff(current, segment.resendts) >= 0:
                # 丢包重传
                need_send = True
                segment.xmit += 1
                self.xmit += 1
                if self.nodelay == 0:
                    segment.rto += self.rx_rto
                else:
                    segment.rto += self.rx_rto // 2
                segment.resendts = current + segment.rto
                lost = 1
            elif segment.fastack >= resent:
                # 快速重传
                need_send = True
                segment.xmit += 1
                segment.fastack = 0
                segment.resendts = current + segment.rto
                change += 1

            if need_send:
                segment.ts = current
                segment.wnd = seg.wnd
                segment.una = self.rcv_nxt

                need = IKCP_OVERHEAD + len(segment.data)
                if (offset + need) >= self.mtu:
                    self.output(self.buffer, offset)
                    offset = 0
                offset += segment.encode(self.buffer, offset)
                if len(segment.data) > 0:
                    self.buffer[offset: offset + len(segment.data)] = segment.data[:]
                    offset += len(segment.data)
                if segment.xmit >= self.dead_link:
                    self.state = -1
        # flash remain segment
        if offset > 0:
            self.output(self.buffer, offset)

        # update ssthresh
        # 拥塞避免
        if change != 0:
            inflight = self.snd_nxt - self.snd_una
            self.ssthresh = inflight // 2
            if self.ssthresh < IKCP_THRESH_MIN:
                self.ssthresh = IKCP_THRESH_MIN
            self.cwnd = self.ssthresh + resent
            self.incr = self.cwnd * self.mss

        if lost != 0:
            self.ssthresh = self.cwnd // 2
            if self.ssthresh < IKCP_THRESH_MIN:
                self.ssthresh = IKCP_THRESH_MIN
            self.cwnd = 1
            self.incr = self.mss

        if self.cwnd < 1:
            self.cwnd = 1
            self.incr = self.mss

    def update(self, current: int):
        self.current = current

        if 0 == self.updated:
            self.updated = 1
            self.ts_flush = self.current

        # 两次更新间隔
        slap = self._itimediff(self.current, self.ts_flush)

        # interval设置过大或者Update调用间隔太久
        if (slap >= 10000) or (slap < -10000):
            self.ts_flush = self.current
            slap = 0

        if slap >= 0:
            self.ts_flush += self.interval
            if self._itimediff(self.current, self.ts_flush) >= 0:
                self.ts_flush = self.current + self.interval
            self.flush()

    def check(self, current):
        ts_flush = self.ts_flush
        tm_packet = 0x7ffffff
        if self.updated == 0:
            return current
        if (self._itimediff(current, ts_flush) >= 10000) or (self._itimediff(current, ts_flush) < -10000):
            ts_flush = current

        if self._itimediff(current, ts_flush) >= 0:
            return current
        tm_flush = self._itimediff(ts_flush, current)
        for seg in self.nsnd_buf:
            diff = self._itimediff(seg.resendts, current)
            if diff <= 0:
                return current
            if diff < tm_packet:
                tm_packet = diff
        minimal = tm_packet if (tm_packet < tm_flush) else tm_flush
        if minimal >= self.interval:
            minimal = self.interval

        return current + minimal

    def set_mtu(self, mtu):
        if (mtu < 50) or (mtu < IKCP_OVERHEAD):
            return -1
        self.buffer = bytes((self.mtu + IKCP_OVERHEAD) * 3)
        self.mtu = mtu
        self.mss = self.mtu - IKCP_OVERHEAD
        return 0

    def set_interval(self, interval):
        if interval > 5000:
            interval = 5000
        elif interval < 10:
            interval = 10
        self.interval = interval
        return 0

    def set_nodelay(self, nodelay, interval, resend, nc):
        if nodelay >= 0:
            self.nodelay = nodelay
            if nodelay != 0:
                self.rx_minrto = IKCP_RTO_NDL
            else:
                self.rx_minrto = IKCP_RTO_MIN
        self.set_interval(interval)
        if resend >= 0:
            self.fastresend = resend
        if nc >= 0:
            self.nocwnd = nc
        return 0

    def wnd_size(self, snd_wnd, rcv_wnd):
        if snd_wnd > 0:
            self.snd_wnd = snd_wnd
        if rcv_wnd > 0:
            self.rcv_wnd = rcv_wnd
        return 0

    def wait_snd(self):
        return len(self.nsnd_buf) + len(self.nsnd_que)

    def output(self, buffer: bytearray, size):
        raise NotImplementedError
