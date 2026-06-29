# ACID BLE - raw HCI USER-channel advertiser engine (Broadcom/Pi). Educational / own-lab.
# Reusable: HCI().open() -> takes EXCLUSIVE control of hci0 (BlueZ can't override),
# then set_random_addr/set_params/set_data/enable to advertise. close() restores BlueZ.
import socket, struct, ctypes, ctypes.util, fcntl, time, subprocess

AF_BLUETOOTH = 31; BTPROTO_HCI = 1; HCI_CHANNEL_USER = 1; HCIDEVDOWN = 0x400448ca

class HCI:
    def __init__(self, dev=0):
        self.dev = dev
        self.s = None

    def open(self):
        # free the controller from bluetoothd, bring it down, take exclusive USER channel
        subprocess.run(['systemctl', 'stop', 'bluetooth'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(1)
        try:
            d = socket.socket(AF_BLUETOOTH, socket.SOCK_RAW, BTPROTO_HCI)
            try: fcntl.ioctl(d.fileno(), HCIDEVDOWN, self.dev)
            except Exception: pass
            d.close()
        except Exception: pass
        libc = ctypes.CDLL(ctypes.util.find_library('c') or 'libc.so.6', use_errno=True)
        self.s = socket.socket(AF_BLUETOOTH, socket.SOCK_RAW, BTPROTO_HCI)
        sa = struct.pack('<HHH', AF_BLUETOOTH, self.dev, HCI_CHANNEL_USER)
        if libc.bind(self.s.fileno(), sa, len(sa)) != 0:
            raise OSError(ctypes.get_errno(), 'HCI USER-channel bind failed')
        self._raw(0x0c03)   # HCI Reset
        time.sleep(0.2)

    def _raw(self, opcode, data=b''):
        try: self.s.send(struct.pack('<BHB', 0x01, opcode, len(data)) + data)
        except Exception: pass
        time.sleep(0.002)

    def _le(self, ocf, data=b''):
        self._raw(ocf | (0x08 << 10), data)

    def set_random_addr(self, addr6):
        self._le(0x0005, addr6)

    def set_params(self, interval=0x00A0):
        # min=max interval, adv_type=3 (non-connectable), own_addr_type=1 (random), all 3 channels
        self._le(0x0006, struct.pack('<HHBBB', interval, interval, 3, 1, 0) + b'\x00' * 6 + struct.pack('<BB', 0x07, 0x00))

    def set_data(self, adv):
        adv = adv[:31]
        self._le(0x0008, bytes([len(adv)]) + adv + b'\x00' * (31 - len(adv)))

    def enable(self, on):
        self._le(0x000a, bytes([1 if on else 0]))

    def close(self):
        try: self.enable(False)
        except Exception: pass
        try: self.s.close()
        except Exception: pass
        subprocess.run(['hciconfig', 'hci0', 'up'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        subprocess.run(['systemctl', 'start', 'bluetooth'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
