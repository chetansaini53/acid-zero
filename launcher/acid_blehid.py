#!/usr/bin/env python3
"""
Acid Zero - BLE HID media-remote daemon (Pi side).

Turns the Pi's onboard Bluetooth into a **BLE HID peripheral** (HID-over-GATT /
HOGP) that presents itself as "Acid Zero Remote". A phone/tablet/PC (e.g. an iPad)
pairs with it from its own Bluetooth settings - the Pi advertises, the host
connects (that is how HID works: the remote is the peripheral, the host is the
central; the Pi does not "search" for the host).

Once connected, the launcher's Bluetooth-Remote plugin drives it: each line on
stdin is a media command -> a Consumer-Control HID report is sent to the host.

    playpause | volup | voldown | next | prev | mute | stop

Connection state is published to /run/acid_blehid.json for the UI. This runs as
its own process (owns the glib mainloop + dbus) started/stopped by the plugin.

Needs BlueZ 5.56+ with the Experimental D-Bus API (LEAdvertisingManager +
notifying secure characteristics). Educational / own-lab use only.

Report map + HID service structure adapted from HeadHodge's public HOGP example.
"""
import json
import os
import sys

import dbus
import dbus.mainloop.glib
import dbus.service

try:
    from gi.repository import GLib
except ImportError:
    import glib as GLib  # pragma: no cover

BLUEZ = "org.bluez"
GATT_MANAGER = "org.bluez.GattManager1"
LE_ADV_MANAGER = "org.bluez.LEAdvertisingManager1"
GATT_SVC_IFACE = "org.bluez.GattService1"
GATT_CHR_IFACE = "org.bluez.GattCharacteristic1"
GATT_DSC_IFACE = "org.bluez.GattDescriptor1"
DBUS_OM = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP = "org.freedesktop.DBus.Properties"
LE_ADV_IFACE = "org.bluez.LEAdvertisement1"
DEVICE_IFACE = "org.bluez.Device1"
AGENT_IFACE = "org.bluez.Agent1"
AGENT_MANAGER = "org.bluez.AgentManager1"
AGENT_PATH = "/acidzero/hid/agent"

STATE_FILE = "/run/acid_blehid.json"
ADV_NAME = "Acid Zero Remote"

# Consumer-Control (HID usage page 0x0C) 16-bit usage codes -> media keys.
MEDIA = {
    "playpause": 0x00CD, "volup": 0x00E9, "voldown": 0x00EA,
    "next": 0x00B5, "prev": 0x00B6, "mute": 0x00E2, "stop": 0x00B7,
}


def _publish(connected, central=""):
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump({"advertising": True, "connected": bool(connected),
                       "central": central[:24], "name": ADV_NAME}, f)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


# ---------------------------- GATT base classes ----------------------------
class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = "/acidzero/hid"
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, svc):
        self.services.append(svc)

    @dbus.service.method(DBUS_OM, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        out = {}
        for s in self.services:
            out[s.get_path()] = s.get_properties()
            for c in s.chars:
                out[c.get_path()] = c.get_properties()
                for d in c.descs:
                    out[d.get_path()] = d.get_properties()
        return out


class Service(dbus.service.Object):
    def __init__(self, bus, index, uuid, primary=True):
        self.path = "/acidzero/hid/service%d" % index
        self.uuid = uuid
        self.primary = primary
        self.chars = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_char(self, c):
        self.chars.append(c)

    def get_properties(self):
        return {GATT_SVC_IFACE: {
            "UUID": self.uuid, "Primary": self.primary,
            "Characteristics": dbus.Array([c.get_path() for c in self.chars], signature="o")}}


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, svc, uuid, flags):
        self.path = svc.path + "/char%d" % index
        self.uuid = uuid
        self.flags = flags
        self.service = svc
        self.descs = []
        self.value = [dbus.Byte(0), dbus.Byte(0)]
        self.notifying = False
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_desc(self, d):
        self.descs.append(d)

    def get_properties(self):
        return {GATT_CHR_IFACE: {
            "Service": self.service.get_path(), "UUID": self.uuid,
            "Flags": self.flags,
            "Descriptors": dbus.Array([d.get_path() for d in self.descs], signature="o")}}

    @dbus.service.method(DBUS_PROP, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return self.get_properties()[GATT_CHR_IFACE]

    @dbus.service.method(GATT_CHR_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        return self.value

    @dbus.service.method(GATT_CHR_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        self.value = value

    @dbus.service.method(GATT_CHR_IFACE)
    def StartNotify(self):
        self.notifying = True
        sys.stderr.write("StartNotify on %s\n" % self.uuid); sys.stderr.flush()

    @dbus.service.method(GATT_CHR_IFACE)
    def StopNotify(self):
        self.notifying = False

    @dbus.service.signal(DBUS_PROP, signature="sa{sv}as")
    def PropertiesChanged(self, iface, changed, invalidated):
        pass

    def notify(self, data):
        if not self.notifying:
            return
        self.PropertiesChanged(
            GATT_CHR_IFACE,
            {"Value": dbus.Array([dbus.Byte(b) for b in data], signature="y")}, [])


class Descriptor(dbus.service.Object):
    def __init__(self, bus, index, chrc, uuid, flags, value):
        self.path = chrc.path + "/desc%d" % index
        self.uuid = uuid
        self.flags = flags
        self.chrc = chrc
        self.value = value
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {GATT_DSC_IFACE: {
            "Characteristic": self.chrc.get_path(), "UUID": self.uuid, "Flags": self.flags}}

    @dbus.service.method(GATT_DSC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        return self.value


# ---------------------------- HID + battery services ----------------------------
# Report ID 1 = keyboard, Report ID 2 = Consumer Control (16-bit media usage).
REPORT_MAP = bytearray.fromhex(
    "05010906a1018501050719e029e71500250175019508810295017508150025650507190029658100c0"
    "050C0901A101850275109501150126ff0719012Aff078100C0")


class HIDService(Service):
    def __init__(self, bus, index):
        Service.__init__(self, bus, index, "1812")
        # HID Information: bcdHID 1.11, country 0, flags RemoteWake|NormallyConnectable
        info = Characteristic(bus, 0, self, "2A4A", ["read"])
        info.value = [dbus.Byte(x) for x in (0x11, 0x01, 0x00, 0x03)]
        # Report Map
        rmap = Characteristic(bus, 1, self, "2A4B", ["read"])
        rmap.value = [dbus.Byte(b) for b in REPORT_MAP]
        # HID Control Point (write-no-response)
        ctrl = Characteristic(bus, 2, self, "2A4C", ["write-without-response"])
        # Protocol Mode
        pmode = Characteristic(bus, 3, self, "2A4E", ["read", "write-without-response"])
        pmode.value = [dbus.Byte(0x01)]
        # Report - keyboard (ID 1, input)
        self.kbd = Characteristic(bus, 4, self, "2A4D", ["read", "notify"])
        self.kbd.add_desc(Descriptor(bus, 0, self.kbd, "2908", ["read"], [dbus.Byte(1), dbus.Byte(1)]))
        # Report - consumer/media (ID 2, input)
        self.media = Characteristic(bus, 5, self, "2A4D", ["read", "notify"])
        self.media.add_desc(Descriptor(bus, 0, self.media, "2908", ["read"], [dbus.Byte(2), dbus.Byte(1)]))
        for c in (info, rmap, ctrl, pmode, self.kbd, self.media):
            self.add_char(c)

    def press(self, name):
        code = MEDIA.get(name)
        if code is None:
            return
        sys.stderr.write("press %s notifying=%s\n" % (name, self.media.notifying)); sys.stderr.flush()
        self.media.notify([code & 0xFF, (code >> 8) & 0xFF])  # press
        self.media.notify([0x00, 0x00])                        # release

    def key(self, mod, code):
        """Keyboard report ID 1: [modifier byte, keycode]. Tap = press + release."""
        self.kbd.notify([mod & 0xFF, code & 0xFF])
        self.kbd.notify([0x00, 0x00])


class BatteryService(Service):
    def __init__(self, bus, index):
        Service.__init__(self, bus, index, "180F")
        lvl = Characteristic(bus, 0, self, "2A19", ["read", "notify"])
        lvl.value = [dbus.Byte(100)]
        self.add_char(lvl)


# ---------------------------- advertisement ----------------------------
class Advertisement(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = "/acidzero/hid/adv%d" % index
        self.bus = bus
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return {
            "Type": "peripheral",
            "ServiceUUIDs": dbus.Array(["1812"], signature="s"),
            "LocalName": dbus.String(ADV_NAME),
            "Appearance": dbus.UInt16(0x03C1),   # HID Keyboard (remotes advertise as keyboard)
            "Discoverable": dbus.Boolean(True),
        }

    @dbus.service.method(LE_ADV_IFACE)
    def Release(self):
        pass


# ---------------------------- pairing agent (auto-accept "just works") ----------------------------
class Agent(dbus.service.Object):
    """NoInputNoOutput agent: auto-accepts pairing so a phone/tablet/PC bonds with
    the remote without a PIN (the reason a fresh adapter rejects the pair request)."""

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        return  # accept

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        return "0000"

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_IFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        pass

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        pass

    @dbus.service.method(AGENT_IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        # Numeric comparison: publish the 6-digit code so the UI shows it (the host
        # shows the same one); accept on the Pi side - the user verifies on the host.
        try:
            with open("/run/acid_blehid.pair", "w") as f:
                f.write("%06d" % int(passkey))
        except Exception:
            pass
        return  # accept

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        return  # accept

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Cancel(self):
        pass


# ---------------------------- daemon ----------------------------
def _find_adapter(bus):
    om = dbus.Interface(bus.get_object(BLUEZ, "/"), DBUS_OM)
    for path, ifaces in om.GetManagedObjects().items():
        if GATT_MANAGER in ifaces and LE_ADV_MANAGER in ifaces:
            return path
    return None


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = _find_adapter(bus)
    if not adapter:
        _publish(False)
        sys.stderr.write("no BLE adapter with GATT+Adv managers\n")
        return

    props = dbus.Interface(bus.get_object(BLUEZ, adapter), DBUS_PROP)
    props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
    props.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(True))       # <-- was the reject cause
    try:
        props.Set("org.bluez.Adapter1", "PairableTimeout", dbus.UInt32(0))
        props.Set("org.bluez.Adapter1", "Alias", dbus.String(ADV_NAME))
    except Exception:
        pass

    # Auto-accept pairing: register a NoInputNoOutput agent as the default.
    try:
        Agent(bus, AGENT_PATH)
        am = dbus.Interface(bus.get_object(BLUEZ, "/org/bluez"), AGENT_MANAGER)
        am.RegisterAgent(AGENT_PATH, "DisplayYesNo")   # numeric comparison (show + confirm)
        am.RequestDefaultAgent(AGENT_PATH)
    except Exception as e:
        sys.stderr.write("agent register failed: %s\n" % e); sys.stderr.flush()

    app = Application(bus)
    hid = HIDService(bus, 0)
    app.add_service(BatteryService(bus, 1))
    app.add_service(hid)

    gatt = dbus.Interface(bus.get_object(BLUEZ, adapter), GATT_MANAGER)
    adv = Advertisement(bus, 0)
    admgr = dbus.Interface(bus.get_object(BLUEZ, adapter), LE_ADV_MANAGER)

    def _reg_err(what):
        def cb(e):
            sys.stderr.write("%s register ERROR: %s\n" % (what, e)); sys.stderr.flush()
        return cb

    def _reg_ok(what):
        def cb():
            sys.stderr.write("%s registered OK\n" % what); sys.stderr.flush()
        return cb

    gatt.RegisterApplication(app.get_path(), {},
                             reply_handler=_reg_ok("GATT"), error_handler=_reg_err("GATT"))
    admgr.RegisterAdvertisement(adv.get_path(), {},
                                reply_handler=_reg_ok("ADV"), error_handler=_reg_err("ADV"))
    _publish(False)

    # Track connection state: watch every Device1 Connected property under the adapter.
    def _on_props(iface, changed, inv, path=None):
        if iface != DEVICE_IFACE or "Connected" not in changed:
            return
        conn = bool(changed["Connected"])
        if conn:
            try: os.remove("/run/acid_blehid.pair")   # pairing done, drop the code
            except Exception: pass
        try:
            dev = dbus.Interface(bus.get_object(BLUEZ, path), DBUS_PROP)
            name = str(dev.Get(DEVICE_IFACE, "Name"))
        except Exception:
            name = ""
        _publish(conn, name)
    bus.add_signal_receiver(_on_props, dbus_interface=DBUS_PROP,
                            signal_name="PropertiesChanged", arg0=DEVICE_IFACE,
                            path_keyword="path")

    # Read media commands from stdin (the plugin writes one per line).
    def _on_stdin(source, cond):
        line = source.readline()
        if not line:
            return False
        cmd = line.strip()
        low = cmd.lower()
        if low == "quit":
            loop.quit()
            return False
        if low.startswith("k "):                 # keyboard: "k <modifier> <keycode>"
            p = cmd.split()
            if len(p) == 3:
                try:
                    hid.key(int(p[1]), int(p[2]))
                except Exception as e:
                    sys.stderr.write("key: %s\n" % e)
            return True
        if low in MEDIA:
            try:
                hid.press(low)
            except Exception as e:
                sys.stderr.write("press %s: %s\n" % (low, e))
        return True

    GLib.io_add_watch(sys.stdin, GLib.IO_IN, _on_stdin)

    loop = GLib.MainLoop()
    try:
        loop.run()
    finally:
        try:
            admgr.UnregisterAdvertisement(adv.get_path())
            gatt.UnregisterApplication(app.get_path())
        except Exception:
            pass
        try:
            os.remove(STATE_FILE)
        except Exception:
            pass


if __name__ == "__main__":
    main()
