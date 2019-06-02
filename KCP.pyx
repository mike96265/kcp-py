cdef extern from 'stdlib.h':
    void *malloc(size_t size);
    void free(void *ptr)

cdef extern from "strings.h":
    void *memcpy(void *str1, const void *str2, size_t n)

cdef void ikcp_encode8u(char *p, int offset, int c):
    p[0 + offset] = c & 255

cdef int ikcp_decode8u(char *p, int offset):
    return p[0 + offset]

cdef void ikcp_encode16u(char *p, int offset, int w):
    p[offset + 0] = (w >> 8) & 255
    p[offset + 1] = (w >> 0) & 255

cdef int ikcp_decode16u(char *p, int offset):
    return (p[0 + offset] & 0xff) << 8 | (p[1 + offset] & 0xff)

cdef void ikcp_encode32u(char *p, int offset, int l):
    p[offset + 0] = (l >> 24) & 255
    p[offset + 1] = (l >> 16) & 255
    p[offset + 2] = (l >> 8) & 255
    p[offset + 3] = (l >> 0) & 255

cdef int ikcp_decode32u(char *p, int offset):
    return (p[offset + 0] & 0xff) << 24 \
           | (p[offset + 1] & 0xff) << 16 \
           | (p[offset + 2] & 0xff) << 8 \
           | p[offset + 3] & 0xff

cdef int _imin_(int a, int b):
    return a if a <= b else b

cdef int _imax_(int a, int b):
    return a if a >= b else b

cdef int _ibound_(int lower, int middle, int upper):
    return _imin_(_imax_(lower, middle), upper)

cdef int _itimediff(int later, int earlier):
    return <int> later - earlier

cdef class Segment:
    cdef:
        int conv, cmd, frg, wnd, ts, sn, una, resendts, rto, fastack, xmit, size
        char *data

    def __cinit__(self, size):
        self.conv = 0
        self.cmd = 0
        self.frg = 0
        self.wnd = 0
        self.ts = 0
        self.sn = 0
        self.una = 0
        self.resendts = 0
        self.rto = 0
        self.fastack = 0
        self.xmit = 0
        self.size = size
        self.data = <char*> malloc(sizeof(char) * size)
        if self.data == NULL:
            raise MemoryError()

    def __dealloc__(self):
        if self.data != NULL:
            free(self.data)

    cdef int encode(self, char*ptr, int offset):
        cdef int _offset = offset
        ikcp_encode32u(ptr, offset, self.conv)
        offset += 4

        ikcp_encode8u(ptr, offset, self.cmd)
        offset += 1

        ikcp_encode8u(ptr, offset, self.frg)
        offset += 1

        ikcp_encode16u(ptr, offset, self.wnd)
        offset += 2

        ikcp_encode32u(ptr, offset, self.ts)
        offset += 4

        ikcp_encode32u(ptr, offset, self.sn)
        offset += 4

        ikcp_encode32u(ptr, offset, self.una)
        offset += 4

        ikcp_encode32u(ptr, offset, self.size)

        return offset - _offset

cdef int IKCP_RTO_NDL = 30  # no delay min rto
cdef int IKCP_RTO_MIN = 100  # normal min rto
cdef int IKCP_RTO_DEF = 200
cdef int IKCP_RTO_MAX = 60000
cdef int IKCP_CMD_PUSH = 81  # cmd: push data
cdef int IKCP_CMD_ACK = 82  # cmd: ack
cdef int IKCP_CMD_WASK = 83  # cmd: window probe (ask)
cdef int IKCP_CMD_WINS = 84  # cmd: window size (tell)
cdef int IKCP_ASK_SEND = 1  # need to send IKCP_CMD_WASK
cdef int IKCP_ASK_TELL = 2  # need to send IKCP_CMD_WINS
cdef int IKCP_WND_SND = 32
cdef int IKCP_WND_RCV = 32
cdef int IKCP_MTU_DEF = 1400
cdef int IKCP_ACK_FAST = 3
cdef int IKCP_INTERVAL = 100
cdef int IKCP_OVERHEAD = 24
cdef int IKCP_DEADLINK = 10
cdef int IKCP_THRESH_INIT = 2
cdef int IKCP_THRESH_MIN = 2
cdef int IKCP_PROBE_INIT = 7000  # 7 secs to probe window size
cdef int IKCP_PROBE_LIMIT = 120000  # up to 120 secs to probe window

cdef class KCP:
    cdef public int conv
    cdef:
        int snd_una, snd_nxt, rcv_nxt
        int ts_recent, ts_lastack, ts_probe, probe_wait
        int snd_wnd, rec_wnd, rmt_wnd
        int cwnd, incr, probe, mtu, mss
        int state, dead_link
        int rx_srtt, rx_rttval, rx_rto, rx_minrto
        int current, interval, ts_flush, nodelay, updated, logmask, ssthresh
        int fastresend, nocwnd, xmit
        char*buffer
        list nrcv_buf, nsnd_buf, nrcv_que, nsnd_que, acklist

    def __cinit__(self, conv):
        self.conv = conv
        self.snd_una = 0
        self.snd_nxt = 0
        self.rcv_nxt = 0
        self.ts_recent = 0
        self.ts_lastack = 0
        self.ts_probe = 0
        self.probe_wait = 0
        self.snd_wnd = IKCP_WND_SND
        self.rcv_wnd = IKCP_WND_RCV
        self.rmt_wnd = IKCP_WND_RCV
        self.cwnd = 0
        self.incr = 0
        self.probe = 0
        self.mtu = IKCP_MTU_DEF
        self.mss = self.mtu - IKCP_OVERHEAD
        self.state = 0
        self.rx_srtt = 0
        self.rx_rttval = 0
        self.rx_rto = IKCP_RTO_DEF
        self.rx_minrto = IKCP_RTO_MIN
        self.current = 0
        self.interval = IKCP_INTERVAL
        self.ts_flush = IKCP_INTERVAL
        self.nodelay = 0
        self.updated = 0
        self.logmask = 0
        self.ssthresh = IKCP_THRESH_INIT
        self.fastresend = 0
        self.nocwnd = 0
        self.xmit = 0
        self.dead_link = IKCP_DEADLINK
        self.buffer = <char*> malloc(sizeof(char) * (self.mtu + IKCP_OVERHEAD) * 3)
        self.nrcv_buf = list()
        self.nsnd_buf = list()
        self.nrcv_que = list()
        self.nsnd_que = list()
        self.acklist = list()

    def __dealloc__(self):
        free(self.buffer)

    cpdef int recv(self, char *buffer, int size):
        if not len(self.nrcv_que):
            return -1
        cdef int peeksize = self.peeksize()
        if peeksize < 0:
            return -2
        if peeksize > size:
            return -3
        cdef bint recover = False
        if len(self.nrcv_que) >= self.rcv_wnd:
            recover = True

        cdef int count = 0
        cdef int n = 0

        cdef Segment seg

        for seg in self.nrcv_que:
            memcpy(seg.data, buffer, seg.size)
            buffer += seg.size
            count += 1
            if seg.frg == 0:
                break

        if count > 0:
            self.nrcv_que = self.nrcv_que[count:]

        count = 0

        for seg in self.nrcv_buf:
            if (seg.sn == self.rcv_nxt) and (len(self.nrcv_que) < self.rcv_wnd):
                self.nrcv_que.append(seg)
                self.rcv_nxt += 1
                count += 1
            else:
                break
        if count > 0:
            self.nrcv_buf = self.nrcv_buf[count:]

        if (len(self.nrcv_que) < self.rcv_wnd) and recover:
            self.probe |= IKCP_ASK_SEND
        return 1

    cpdef int peeksize(self):
        if 0 == len(self.nrcv_que):
            return -1
        cdef Segment seg = self.nrcv_que[0]
        if seg.frg == 0:
            return seg.size
        if len(self.nrcv_que) < (seg.frg + 1):
            return -1
        cdef int length = 0
        for seg in self.nrcv_que:
            length += seg.size
            if seg.frg == 0:
                break
        return length

    cpdef int send(self, char*buffer, int size):
        cdef int count
        if size < self.mss:
            count = 1
        else:
            count = (size + self.mss - 1) / self.mss

        if count > 255:
            return -2

        if count == 0:
            count = 1

        cdef int i, seg_size
        cdef Segment seg

        for i in range(count):
            seg_size = self.mss if (size > self.mss) else size
            seg = Segment(seg_size)
            memcpy(buffer, seg.data, seg_size)
            buffer += seg_size
            seg.frg = count - i - 1
            self.nrcv_que.append(seg)
            size -= seg_size
        return 0

    cdef void update_ack(self, int rtt):
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
        self.rx_rto = _ibound_(self.rx_minrto, rto, IKCP_RTO_MAX)

    cdef void shrink_buf(self):
        """计算本地真实snd_una"""
        if len(self.nsnd_buf) > 0:
            self.snd_una = self.nsnd_buf[0].sn
        else:
            self.snd_una = self.snd_nxt

    cdef void parse_ack(self, int sn):
        """对端返回的ack，确认发送成功时，对应包从发送缓存中移除"""
        if (_itimediff(sn, self.snd_una) < 0) or (_itimediff(sn, self.snd_nxt) >= 0):
            return
        cdef int index = 0
        cdef Segment segment
        for segment in self.nsnd_buf:
            if _itimediff(sn, segment.sn) < 0:
                break
            segment.fastack += 1
            if sn == segment.sn:
                self.nsnd_buf.pop(index)
                break
            index += 1

    cdef parse_una(self, int una):
        """通过对端传回的una将已经确认发送成功的包从发送缓存中移除"""
        count = 0
        for segment in self.nsnd_buf:
            if _itimediff(una, segment.sn) > 0:
                count += 1
            else:
                break
        if count > 0:
            self.nsnd_buf = self.nsnd_buf[count:]

    cdef ack_push(self, int sn, int ts):
        """收到数据包之后，将对应ack返回，flush时发送"""
        self.acklist.append(sn)
        self.acklist.append(ts)


    def parse_data(self, Segment new_segment):
        """用户数据包解析"""
        sn = new_segment.sn
        cdef bint repeat = False
        cdef int after_idx = -1

        if (_itimediff(sn, self.rcv_nxt + self.rcv_wnd) >= 0) or (_itimediff(sn, self.rcv_nxt) < 0):
            return
        n = len(self.nrcv_buf) - 1

        # 判断是否重复包，同时计算插入位置
        cdef int i
        cdef Segment segment
        for i in range(n, -1, -1):
            segment = self.nrcv_buf[i]
            if segment.sn == sn:
                repeat = True
                break
            if _itimediff(sn, segment.sn) > 0:
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

    cpdef input(self, char *data, int size):
        cdef int s_una = self.snd_una
        if size < IKCP_OVERHEAD:
            return 0
        cdef int offset
        cdef int cmd, frg, wnd, ts, sn, una, length
        cdef Segment segment
        while True:
            """解析data"""
            offset = 0
            if (size - offset) < IKCP_OVERHEAD:
                break
            conv = ikcp_decode32u(data, offset)
            offset += 4
            if self.conv != conv:
                return -1
            cmd = ikcp_decode8u(data, offset)
            offset += 1
            frg = ikcp_decode8u(data, offset)
            offset += 1
            wnd = ikcp_decode16u(data, offset)
            offset += 2
            ts = ikcp_decode32u(data, offset)
            offset += 4
            sn = ikcp_decode32u(data, offset)
            offset += 4
            una = ikcp_decode32u(data, offset)
            offset += 4
            length = ikcp_decode32u(data, offset)
            offset += 4
            """长度不对"""
            if (size - offset) < length:
                return -2
            data += offset
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
                """ack 包"""
                if _itimediff(self.current, ts) >= 0:
                    self.update_ack(_itimediff(self.current, ts))
                self.parse_ack(sn)
                self.shrink_buf()
            elif IKCP_CMD_PUSH == cmd:
                """数据包"""
                if _itimediff(sn, self.rcv_nxt + self.rcv_wnd) < 0:
                    self.ack_push(sn, ts)
                    if _itimediff(sn, self.rcv_nxt) >= 0:
                        segment = Segment(length)
                        segment.conv = conv
                        segment.cmd = cmd
                        segment.frg = frg
                        segment.wnd = wnd
                        segment.ts = ts
                        segment.sn = sn
                        segment.una = una
                        if length > 0:
                            memcpy(data, segment.data, offset + length)
                            data += length
                        self.parse_data(segment)
            elif IKCP_CMD_WASK == cmd:
                self.probe |= IKCP_ASK_TELL
            elif IKCP_CMD_WINS == cmd:
                pass
            else:
                return -3
        if _itimediff(self.snd_una, s_una) > 0:
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

    cdef int wnd_unused(self):
        if len(self.nrcv_que) < self.rcv_wnd:
            return self.rcv_wnd - len(self.nrcv_que)
        return 0

    cdef flush(self):
        cdef int current, change, lost
        current = self.current
        change = 0
        lost = 0

        if self.updated == 0:
            return

        cdef Segment seg = Segment(0)
        seg.conv = self.conv
        seg.cmd = IKCP_CMD_ACK
        seg.wnd = self.wnd_unused()
        seg.una = self.rcv_nxt

        cdef int count, offset, i
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
                if _itimediff(self.current, self.ts_probe) >= 0:
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
        cdef int cwnd = _imin_(self.snd_wnd, self.rmt_wnd)

        # 如果采用拥塞控制
        if self.nocwnd == 0:
            cwnd = _imin_(self.cwnd, cwnd)

        count = 0

        # move data from snd_queue to snd_buf
        cdef Segment new_segment, nsnd_que_item
        for nsnd_que_item in self.nsnd_que:
            if (_itimediff(self.snd_nxt, self.snd_una + cwnd)) >= 0:
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
        cdef int resent, rtomin
        resent = self.fastresend if (self.fastresend > 0) else 0xffffffff
        rtomin = (self.rx_rto >> 3) if (self.nodelay == 0) else 0

        # flush data segment
        cdef Segment segment
        cdef bint need_send
        for segment in self.nsnd_buf:
            need_send = False
            if segment.xmit == 0:
                # 第一次传输
                need_send = True
                segment.xmit += 1
                segment.rto = self.rx_rto
                segment.resendts = current + segment.rto + rtomin
            elif _itimediff(current, segment.resendts) >= 0:
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
        cdef int inflight
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

    cpdef update(self, long int current):
        self.current = current

        if 0 == self.updated:
            self.updated = 1
            self.ts_flush = self.current

        # 两次更新间隔
        cdef int slap = _itimediff(self.current, self.ts_flush)

        # interval设置过大或者Update调用间隔太久
        if (slap >= 10000) or (slap < -10000):
            self.ts_flush = self.current
            slap = 0

        if slap >= 0:
            self.ts_flush += self.interval
            if _itimediff(self.current, self.ts_flush) >= 0:
                self.ts_flush = self.current + self.interval
            self.flush()

    cpdef long int check(self, current):
        cdef long int ts_flush = self.ts_flush
        cdef int tm_packet = 0x7ffffff
        cdef int tm_flush
        if self.updated == 0:
            return current
        if (_itimediff(current, ts_flush) >= 10000) or (_itimediff(current, ts_flush) < -10000):
            ts_flush = current

        if _itimediff(current, ts_flush) >= 0:
            return current
        tm_flush = _itimediff(ts_flush, current)
        cdef Segment seg
        for seg in self.nsnd_buf:
            diff = _itimediff(seg.resendts, current)
            if diff <= 0:
                return current
            if diff < tm_packet:
                tm_packet = diff
        minimal = tm_packet if (tm_packet < tm_flush) else tm_flush
        if minimal >= self.interval:
            minimal = self.interval
        return current + minimal

    cpdef bint set_mtu(self, int mtu):
        if (mtu < 50) or (mtu < IKCP_OVERHEAD):
            return False
        self.mtu = mtu
        self.mss = self.mtu - IKCP_OVERHEAD
        free(self.buffer)
        cdef char *buffer = <char*> malloc(sizeof(char) * (self.mtu + IKCP_OVERHEAD) * 3)
        if buffer == NULL:
            raise MemoryError()
        self.buffer = buffer
        return 0

    cpdef int set_interval(self, int interval):
        if interval > 5000:
            interval = 5000
        elif interval < 10:
            interval = 10
        self.interval = interval
        return 0

    cpdef bint set_nodelay(self, int nodelay, int interval, int resend, int nc):
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
        return True

    cpdef bint wnd_size(self, int snd_wnd, int rcv_wnd):
        if snd_wnd > 0:
            self.snd_wnd = snd_wnd
        if rcv_wnd > 0:
            self.rcv_wnd = rcv_wnd
        return True

    cpdef int wait_snd(self):
        return len(self.nsnd_buf) + len(self.nsnd_que)
