#!/usr/bin/python3

import json
import crcmod
from argparse import ArgumentParser
from pathlib import Path
import serial
from serial import Serial

DEFAULT_DEVICE = '/dev/ttyS4'
DEFAULT_BAUD_RATE = 3000000
CRC_FN = crcmod.predefined.mkCrcFun('crc-ccitt-false')


def setup_device(port, baudrate):
    # definition from DSDT
    return Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        rtscts=False,
        dsrdtr=False,
        timeout=0,
    )


def crc(pld):
    x = CRC_FN(bytes(pld))
    return [x & 0xff, (x >> 0x08) & 0xff]


def to_int(bytes):
    return int.from_bytes(bytes, byteorder='little')


class Counters:
    PATH = Path(__file__).parent / '.counters.json'

    @staticmethod
    def load():
        if Counters.PATH.is_file():
            with open(Counters.PATH) as fd:
                data = json.load(fd)
                seq = data['seq']
                cnt = data['cnt']
        else:
            seq = 0x00
            cnt = 0x0000

        return Counters(seq, cnt)

    def __init__(self, seq, cnt):
        self.seq = seq
        self.cnt = cnt

    def store(self):
        with open(Counters.PATH, 'w') as fd:
            data = {'seq': self.seq, 'cnt': self.cnt}
            json.dump(data, fd)

    def inc_seq(self):
        self.seq = (self.seq + 1) & 0xFF

    def inc_cnt(self):
        self.cnt = (self.cnt + 1) & 0xFFFF

    def inc(self):
        self.inc_seq()
        self.inc_cnt()


class Command:
    def __init__(self, rtc, riid, rcid, rsnc=0x01, quiet=True):
        self.rtc = rtc
        self.riid = riid
        self.rcid = rcid
        self.rsnc = rsnc
        self.quiet = quiet

    def _write_msg(self, dev, seq, cnt):
        cnt_lo = cnt & 0xff
        cnt_hi = (cnt >> 0x08) & 0xff

        hdr = [0x80, 0x08, 0x00, seq]
        pld = [0x80, self.rtc, 0x01, 0x00, self.riid, cnt_lo, cnt_hi, self.rcid]
        msg = [0xaa, 0x55] + hdr + crc(hdr) + pld + crc(pld)

        return dev.write(bytes(msg))

    def _write_ack(self, dev, seq):
        hdr = [0x40, 0x00, 0x00, seq]
        msg = [0xaa, 0x55] + hdr + crc(hdr) + [0xff, 0xff]

        return dev.write(bytes(msg))

    def _read_ack(self, dev, exp_seq):
        msg = bytes()
        while len(msg) < 0x0A:
            msg += dev.read(0x0A - len(msg))

        #if not self.quiet:
            #print("received: {}".format(msg.hex()))

        assert msg[0:2] == bytes([0xaa, 0x55])
        assert msg[3:5] == bytes([0x00, 0x00])
        assert msg[6:8] == bytes(crc(msg[2:-4]))
        assert msg[8:] == bytes([0xff, 0xff])

        mty = msg[2]
        seq = msg[5]

        if mty == 0x40:
            assert seq == exp_seq

        return mty == 0x04

    def _read_msg(self, dev, cnt):
        cnt_lo = cnt & 0xff
        cnt_hi = (cnt >> 0x08) & 0xff

        buf = bytes()
        rem = 0x08                          # begin with header length
        while len(buf) < rem:
            buf += dev.read(0x0400)

            # if we got a header, validate it
            if rem == 0x08 and len(buf) >= 0x08:
                hdr = buf[0:8]

                assert hdr[0:3] == bytes([0xaa, 0x55, 0x80])
                assert hdr[-2:] == bytes(crc(hdr[2:-2]))

                rem += hdr[3] + 10          # len(payload) + frame + crc

        hdr = buf[0:8]
        msg = buf[8:hdr[3]+10]
        rem = buf[hdr[3]+10:]

        #if not self.quiet:
            #print("received: {}".format(hdr.hex()))
            #print("received: {}".format(msg.hex()))

        assert msg[0:8] == bytes([0x80, self.rtc, 0x00, 0x01, self.riid, cnt_lo, cnt_hi, self.rcid])
        assert msg[-2:] == bytes(crc(msg[:-2]))

        seq = hdr[5]
        pld = msg[8:-2]

        return seq, pld, rem

    def _read_clean(self, dev, buf=bytes()):
        buf += dev.read(0x0400)                     # make sure we're not missing some bytes

        while buf:
            # get header / detect message type
            if len(buf) >= 0x08:
                if buf[0:3] == bytes([0xaa, 0x55, 0x40]):               # ACK
                    while len(buf) < 0x0A:
                        buf += dev.read(0x0400)

                    #if not self.quiet:
                        #print("ignored ACK: {}".format(buf[:0x0a].hex()))
                    buf = bytes(buf[0x0a:])

                elif buf[0:3] == bytes([0xaa, 0x55, 0x80]):             # response
                    buflen = 0x0a + buf[3]
                    while len(buf) < buflen:
                        buf += dev.read(0x0400)

                    #if not self.quiet:
                        #print("ignored MSG: {}".format(buf[:buflen].hex()))
                    buf = bytes(buf[buflen:])

                elif buf[0:3] == bytes([0x4e, 0x00, 0x53]):             # control message?
                    while len(buf) < 0x19:
                        buf += dev.read(0x0400)

                    if not self.quiet:
                        print("ignored CTRL: {}".format(buf[:0x19].hex()))
                    buf = bytes(buf[0x19:])

                else:                                                   # unknown
                    #if not self.quiet:
                        #print("ignored unknown: {}".format(buf.hex()))
                    assert False

            buf += dev.read(0x0400)

    def run(self, dev, cnt):
        self._read_clean(dev)
        self._write_msg(dev, cnt.seq, cnt.cnt)
        retry = self._read_ack(dev, cnt.seq)

        # retry one time on com failure
        if retry:
            self._write_msg(dev, cnt.seq, cnt.cnt)
            retry = self._read_ack(dev, cnt.seq)

            if retry:
                #if not self.quiet:
                    #print('Communication failure: invalid ACK, try again')
                return

        try:
            if self.rsnc:
                seq, pld, rem = self._read_msg(dev, cnt.cnt)
                self._write_ack(dev, seq)
            else:
                seq, pld, rem = 0, bytes(), bytes()

            self._read_clean(dev, rem)
        finally:
            cnt.inc()

        return self._handle_payload(pld)

    def _handle_payload(self, pld):
        return None


class Gbos(Command):
    def __init__(self, **kwargs):
        super().__init__(0x11, 0x00, 0x0d, **kwargs)

    def _handle_payload(self, pld):
        return {
            'Base Status': hex(pld[0]),
        }


class Psr(Command):
    def __init__(self, bat, **kwargs):
        super().__init__(0x02, bat, 0x0d, **kwargs)

    def _handle_payload(self, pld):
        return {
            'Power Source': hex(to_int(pld[0:4])),
        }


class Sta(Command):
    def __init__(self, bat, **kwargs):
        super().__init__(0x02, bat, 0x01, **kwargs)

    def _handle_payload(self, pld):
        return {
            'Battery Status': hex(to_int(pld[0:4])),
        }


class Bst(Command):
    def __init__(self, bat, **kwargs):
        super().__init__(0x02, bat, 0x03, **kwargs)

    def _handle_payload(self, pld):
        return {
            'State': hex(to_int(pld[0:4])),
            'Present Rate': hex(to_int(pld[4:8])),
            'Remaining Capacity': hex(to_int(pld[8:12])),
            'Present Voltage': hex(to_int(pld[12:16])),
        }


class Bix(Command):
    def __init__(self, bat, **kwargs):
        super().__init__(0x02, bat, 0x02, **kwargs)

    def _handle_payload(self, pld):
        return {
            'Revision': hex(pld[0]),
            'Power Unit': hex(to_int(pld[1:5])),
            'Design Capacity': hex(to_int(pld[5:9])),
            'Last Full Charge Capacity': hex(to_int(pld[9:13])),
            'Technology': hex(to_int(pld[13:17])),
            'Design Voltage': hex(to_int(pld[17:21])),
            'Design Capacity of Warning': hex(to_int(pld[21:25])),
            'Design Capacity of Low': hex(to_int(pld[25:29])),
            'Cycle Count': hex(to_int(pld[29:33])),
            'Measurement Accuracy': hex(to_int(pld[33:37])),
            'Max Sampling Time': hex(to_int(pld[37:41])),
            'Min Sampling Time': hex(to_int(pld[41:45])),
            'Max Averaging Interval': hex(to_int(pld[45:49])),
            'Min Averaging Interval': hex(to_int(pld[49:53])),
            'Capacity Granularity 1': hex(to_int(pld[53:57])),
            'Capacity Granularity 2': hex(to_int(pld[57:61])),
            'Model Number': pld[61:82].decode().rstrip('\0'),
            'Serial Number': pld[82:93].decode().rstrip('\0'),
            'Type': pld[93:98].decode().rstrip('\0'),
            'OEM Information': pld[98:119].decode().rstrip('\0'),
        }


class PrettyBat:
    def __init__(self, bat, **kwargs):
        self.bix = Bix(bat, **kwargs)
        self.bst = Bst(bat, **kwargs)

    def run(self, dev, cnt):
        bix = self.bix.run(dev, cnt)
        bst = self.bst.run(dev, cnt)

        state = int(bst['State'], 0)
        vol = int(bst['Present Voltage'], 0)
        rem_cap = int(bst['Remaining Capacity'], 0)
        full_cap = int(bix['Last Full Charge Capacity'], 0)
        rate = int(bst['Present Rate'], 0)

        bat_states = {
            0: 'None',
            1: 'Discharging',
            2: 'Charging',
            4: 'Critical',
            5: 'Critical (Discharging)',
            6: 'Critical (Charging)',
        }

        bat_state = bat_states[state]
        bat_vol = vol / 1000

        if full_cap <= 0:
            bat_rem_perc = '<unavailable>'
        else:
            bat_rem_perc = "{}%".format(int(rem_cap / full_cap * 100))

        if state == 0x00 or rate == 0:
            bat_rem_life = '<unavailable>'
        else:
            bat_rem_life = "{:.2f}h".format(rem_cap / rate)

        return {
            'State': bat_state,
            'Voltage': "{}V".format(bat_vol),
            'Percentage': bat_rem_perc,
            'Remaining': bat_rem_life,
        }


class BaseLock(Command):
    def __init__(self, lock, **kwargs):
        super().__init__(0x11, 0x00, 0x06 if lock else 0x07, 0x00, **kwargs)


COMMANDS = {
    'lid0.gbos': (Gbos, ()),
    'adp1._psr': (Psr, (0x01,)),
    'bat1._sta': (Sta, (0x01,)),
    'bat1._bst': (Bst, (0x01,)),
    'bat1._bix': (Bix, (0x01,)),
    'bat2._sta': (Sta, (0x02,)),
    'bat2._bst': (Bst, (0x02,)),
    'bat2._bix': (Bix, (0x02,)),

    'bat1.pretty': (PrettyBat, (0x01,)),
    'bat2.pretty': (PrettyBat, (0x02,)),

    'base.lock': (BaseLock, (True,)),
    'base.unlock': (BaseLock, (False,)),
}


def main():
    cli = ArgumentParser(description='Surface Book 2 / Surface Pro (2017) embedded controller requests.')
    cli.add_argument('-d', '--device', default=DEFAULT_DEVICE, metavar='DEV', help='the UART device')
    cli.add_argument('-b', '--baud', default=DEFAULT_BAUD_RATE, type=lambda x: int(x, 0), metavar='BAUD', help='the baud rate')
    cli.add_argument('-c', '--cnt', type=lambda x: int(x, 0), help='overwrite CNT')
    cli.add_argument('-s', '--seq', type=lambda x: int(x, 0), help='overwrite SEQ')
    cli.add_argument('-q', '--quiet', action='store_true', help='do not print debug messages, just results')
    commands = cli.add_subparsers()

    for cmd in COMMANDS.keys():
        parser = commands.add_parser(cmd, help="run request '{}'".format(cmd.upper()))
        parser.set_defaults(command=cmd)

    args = cli.parse_args()

    dev = setup_device(args.device, args.baud)
    cmd = COMMANDS.get(args.command)
    cmd = cmd[0](*cmd[1], quiet=args.quiet)

    cnt = Counters.load()
    if args.seq is not None:
        cnt.seq = args.seq
    if args.cnt is not None:
        cnt.cnt = args.cnt

    try:
        res = cmd.run(dev, cnt)

        if args.quiet:
            for k, v in sorted(res.items()):
                print("{}: {}".format(k, v))
        else:
            import pprint
            print()
            pprint.pprint(res)
            with open("/home/battery-stats/battery_stats.txt", "w") as fout:
                fout.write(pprint.pformat(res))

    finally:
        pass
        #cnt.store()


if __name__ == '__main__':
    main()
