# Copyright (c) 2014, Florian Wesch <fw@dividuum.de>
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
# 
#     Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
# 
#     Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in the
#     documentation and/or other materials provided with the
#     distribution.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import re
import logging

from struct import pack, unpack, Struct
from collections import namedtuple
from cStringIO import StringIO
from itertools import izip
from simplejson import loads as json_loads, dumps as json_dumps

log = logging.getLogger(__name__)

OPTIMIZE = True
# OPTIMIZE = False

DEBUG_PKTS = False
# DEBUG_PKTS = True

class ReadBuffer(object):
    __slots__ = [
        "_max_size", 
        "_buffer_trunc",
        "_buffer_tell", 
        "_buffer_read", 
        "_buffer_write", 
        "_buffer_seek", 
    ]

    def __init__(self, data=""):
        self._max_size = 16384
        buf = StringIO()
        self._buffer_trunc = buf.truncate
        self._buffer_write = buf.write
        self._buffer_read = buf.read
        self._buffer_seek = buf.seek
        self._buffer_tell = buf.tell
        self.init_buffer(data)

    def init_buffer(self, data):
        self._buffer_trunc(0)
        self._buffer_write(data)
        self._buffer_seek(0, 0)

    def append(self, data):
        read_pos = self._buffer_tell()
        if read_pos > self._max_size:
            log.debug("shuffling read buffer")
            self.init_buffer(self._buffer_read())
            read_pos = 0
        self._buffer_seek(0, 2)
        self._buffer_write(data)
        self._buffer_seek(read_pos, 0)

    def read(self, count):
        return self._buffer_read(count)

    def snapshot(self):
        return self._buffer_tell()

    def restore(self, read_pos):
        self._buffer_seek(read_pos, 0)

WriteBuffer = StringIO

def read_varint(b):
    byte = b.read(1)
    if not byte:
        return None
    value = ord(byte)
    if value <= 127:
        return value
    value, shift, quantum = value & 0x7f, 7, value
    while 1:
        byte = b.read(1)
        if not byte:
            return None
        quantum = ord(byte)
        value, shift = value + ((quantum & 0x7f) << shift), shift + 7
        if not quantum & 0x80:
            break
    return value
def write_varint(b, value):
    if value <= 127: # fast path
        b.write(chr(value))
    else:
        shifted_value = True # dummy initialized
        while shifted_value:
            shifted_value = value >> 7
            b.write(chr((value & 0x7f) | (0x80 if shifted_value else 0)))
            value = shifted_value
def size_varint(value):
    size = 1
    while value & ~0x7f:
        size += 1
        value >>= 7
    return size

def read_string(b):
    size = read_varint(b)
    string = b.read(size)
    return string.decode("utf8")
def write_string(b, string):
    encoded = string.encode("utf8")
    write_varint(b, len(encoded))
    b.write(encoded)

def read_json(b):
    return json_loads(read_string(b))
def write_json(b, value):
    return write_string(b, json_dumps(value, separators=(',', ':')))

def read_ushort(b):
    return unpack(">H", b.read(2))[0]
def write_ushort(b, value):
    return b.write(pack(">H", value))

def read_short(b):
    return unpack(">h", b.read(2))[0]
def write_short(b, value):
    return b.write(pack(">h", value))

def read_long(b):
    return unpack(">q", b.read(8))[0]
def write_long(b, value):
    return b.write(pack(">q", value))

def read_ulong(b):
    return unpack(">Q", b.read(8))[0]
def write_ulong(b, value):
    return b.write(pack(">Q", value))

def read_ubyte(b):
    return ord(b.read(1))
def write_ubyte(b, value):
    return b.write(chr(value))

def read_byte(b):
    return unpack(">b", b.read(1))[0]
def write_byte(b, value):
    return b.write(pack(">b", value))

def read_bool(b):
    return b.read(1) == '\x01'
def write_bool(b, value):
    return b.write('\x01' if value else '\x00')

def read_float(b):
    return unpack(">f", b.read(4))[0]
def write_float(b, value):
    return b.write(pack(">f", value))

def read_double(b):
    return unpack(">d", b.read(8))[0]
def write_double(b, value):
    return b.write(pack(">d", value))

def read_int(b):
    return unpack(">i", b.read(4))[0]
def write_int(b, value):
    return b.write(pack(">i", value))

def read_uint(b):
    return unpack(">I", b.read(4))[0]
def write_uint(b, value):
    return b.write(pack(">I", value))

def read_int8(b):
    return read_int(b) / 8.0
def write_int8(b, value):
    write_int(int(value * 8))

def read_int32(b):
    return read_int(b) / 32.0
def write_int32(b, value):
    write_int(int(value * 32))

def read_byte32(b):
    return read_byte(b) / 32.0
def write_byte32(b, value):
    write_byte(int(value * 32))

def read_short_byte_array(b):
    size = read_short(b)
    return b.read(size)
def write_short_byte_array(b, value):
    write_short(b, len(value))
    b.write(value)

def read_int_byte_array(b):
    size = read_int(b)
    return b.read(size)
def write_int_byte_array(b, value):
    write_int(b, len(value))
    b.write(value)

def make_array_reader(count_reader, record_reader):
    def reader(b):
        size = count_reader(b)
        return [record_reader(b) for _ in xrange(size)]
    return reader
def make_array_writer(count_writer, record_writer):
    def writer(b, array):
        count_writer(b, len(array))
        for value in array:
            record_writer(b, value)
    return writer
read_byte_int_array = make_array_reader(read_byte, read_int)
write_byte_int_array = make_array_writer(write_byte, write_int)
read_short_int_array = make_array_reader(read_short, read_int)
write_short_int_array = make_array_writer(write_short, write_int)
read_int_string_array = make_array_reader(read_int, read_string)
write_int_string_array = make_array_writer(write_int, write_string)
read_short_string_array = make_array_reader(read_short, read_string)
write_short_string_array = make_array_writer(write_short, write_string)
read_varint_string_array = make_array_reader(read_varint, read_string)
write_varint_string_array = make_array_writer(write_varint, write_string)

Slot = namedtuple("Slot", "item_id count damage nbt")
def read_slot_array(b):
    slots = []
    num_slots = read_short(b)
    for slot in xrange(num_slots):
        item_id = read_short(b)
        if item_id == -1:
            slots.append(None)
            continue
        count = read_byte(b) 
        damage = read_short(b)
        nbt_size = read_short(b)
        if nbt_size != -1:
            nbt = b.read(nbt_size)
        else:
            nbt = None
        slots.append(Slot(item_id, count, damage, nbt))
    return slots
def write_slot_array(b, slots):
    write_short(b, len(slots))
    for slot in slots:
        write_slot(b, slot)

def read_slot(b):
    item_id = read_short(b)
    if item_id == -1:
        return None
    count = read_byte(b) 
    damage = read_short(b)
    nbt_size = read_short(b)
    if nbt_size != -1:
        nbt = b.read(nbt_size)
    else:
        nbt = None
    return Slot(item_id, count, damage, nbt)
def write_slot(b, slot):
    if slot is None:
        write_short(b, -1)
        return
    write_short(b, slot.item_id)
    write_byte(b, slot.count)
    write_short(b, slot.damage)
    if slot.nbt is not None:
        write_short(b, len(slot.nbt))
        b.write(slot.nbt)
    else:
        write_short(b, -1)

def read_changes(b):
    count = read_short(b)
    size = read_int(b)
    assert size == count * 4
    return [read_uint(b) for _ in xrange(count)]
def write_changes(b, changes):
    write_short(b, len(changes))
    write_int(b, len(changes)*4)
    for change in changes:
        write_uint(b, change)

Vector = namedtuple("Vector", "x y z")
def read_vector(b):
    x = read_int(b)
    y = read_int(b)
    z = read_int(b)
    return Vector(x, y, z)
def write_vector(b, value):
    write_int(b, value.x)
    write_int(b, value.y)
    write_int(b, value.z)

META_READERS = {
    0:  read_byte,
    1:  read_short,
    2:  read_int,
    3:  read_float,
    4:  read_string,
    5:  read_slot,
    6:  read_vector,
}
def read_metadata(b):
    meta = {}
    while 1:
        item = read_ubyte(b)
        if item == 0x7f:
            return meta
        meta_type = item >> 5
        meta[item & 0x1f] = meta_type, META_READERS[meta_type](b)
META_WRITERS = {
    0:  write_byte,
    1:  write_short,
    2:  write_int,
    3:  write_float,
    4:  write_string,
    5:  write_slot,
    6:  write_vector,
}
def write_metadata(b, meta):
    for index, (meta_type, meta_value) in meta.iteritems():
        write_ubyte(b, meta_type << 5 | index & 0x1f)
        META_WRITERS[meta_type](b, meta_value)
    write_ubyte(b, 0x7f)

Property = namedtuple("Property", "value modifiers")
Modifier = namedtuple("Modifier", "uuid amount operation")
def read_property_array(b):
    properties = {}
    num_properties = read_int(b)
    for _ in xrange(num_properties):
        key = read_string(b)
        value, num_modifiers = unpack(">dh", b.read(10))
        modifiers = []
        for _ in xrange(num_modifiers):
            msl, lsl, amount, operation = unpack(">QQdb", b.read(25))
            modifiers.append(Modifier(msl << 64 | lsl, amount, operation))
        properties[key] = Property(value, modifiers)
    return properties
def write_property_array(b, properties):
    write_int(b, len(properties))
    for key, property in properties.iteritems():
        write_string(b, key)
        b.write(pack(">dh", property.value, len(property.modifiers)))
        for modifier in property.modifiers:
            b.write(pack(">QQdb", 
                modifier.uuid >> 64,
                modifier.uuid & 0xffffffffffffffff,
                modifier.amount,
                modifier.operation
            ))

SpeedVector = namedtuple("SpeedVector", "x y z")
ObjectData = namedtuple("ObjectData", "int_val speed")
def read_objdata(b):
    int_val = read_int(b)
    if int_val > 0:
        speed = SpeedVector(*unpack(">hhh", b.read(6)))
    else:
        speed = None
    return ObjectData(int_val, speed)
def write_objdata(b, value):
    write_int(b, value.int_val)
    if value.int_val > 0:
        b.write(pack(">hhh",
            value.speed.x,
            value.speed.y,
            value.speed.z,
        ))

def read_statistic_array(b):
    size = read_varint(b)
    stats = []
    for n in xrange(size):
        name = read_string(b)
        amount = read_varint(b)
        stats.append((name, amount))
    return stats
def write_statistic_array(b, value):
    write_varint(b, len(value))
    for name, amount in value:
        write_string(b, name)
        write_varint(b, amount)

ExplosionRecord = namedtuple("ExplosionRecord", "x y z")
ExplosionFmt = Struct(">bbb")
def read_explosions(b):
    explosions = []
    count = read_int(b)
    coords = b.read(3 * count)
    for i in xrange(0, count*3, 3):
        explosions.append(ExplosionRecord(*ExplosionFmt.unpack(coords[i:i+3])))
    return explosions
def write_explosions(b, explosions):
    write_int(b, len(explosions))
    for record in explosions:
        b.write(ExplosionFmt.pack(record.x, record.y, record.z))

ChunkBulk = namedtuple("ChunkBulk", "sky_light_sent compressed_data chunks")
Chunk = namedtuple("Chunk", "x z primary_bitmap add_bitmap")
def read_map_chunk_bulk(b):
    num_chunks = read_short(b)
    data_size = read_int(b)
    sky_light_sent = read_bool(b)
    compressed_data = b.read(data_size)
    chunks = []
    for n in xrange(num_chunks):
        chunk_x = read_int(b)
        chunk_z = read_int(b)
        primary_bitmap = read_ushort(b)
        add_bitmap = read_ushort(b)
        chunks.append(Chunk(chunk_x, chunk_z, primary_bitmap, add_bitmap))
    return ChunkBulk(sky_light_sent, compressed_data, chunks)
def write_map_chunk_bulk(b, bulk):
    write_short(b, len(bulk.chunks))
    write_int(b, len(bulk.compressed_data))
    write_bool(b, bulk.sky_light_sent)
    b.write(bulk.compressed_data)
    for chunk in bulk.chunks:
        write_int(b, chunk.x)
        write_int(b, chunk.z)
        write_ushort(b, chunk.primary_bitmap)
        write_ushort(b, chunk.add_bitmap)

def read_raw(b):
    ss = b.snapshot()
    pkt_size = read_varint(b)
    if pkt_size is None:
        b.restore(ss)
        return None
    raw = b.read(pkt_size)
    if len(raw) != pkt_size:
        b.restore(ss)
        return None
    return StringIO(raw)

def write_packet(b, pkt):
    raw = StringIO()
    write_varint(raw, pkt.id)
    pkt.emit(raw)
    size = raw.tell()
    write_varint(b, size)
    b.write(raw.getvalue())

PROTOCOL_LINE = re.compile(r"(\w+)\s+(\w+)(?:\s+(.*))?").match
PRIMITIVES = {
    'byte':     ('b', 1, None,          None),
    'ubyte':    ('B', 1, None,          None),
    'bool':     ('?', 1, None,          None),
    'short':    ('h', 2, None,          None),
    'ushort':   ('H', 2, None,          None),
    'int':      ('i', 4, None,          None),
    'long':     ('q', 8, None,          None),
    'float':    ('f', 4, None,          None),
    'double':   ('d', 8, None,          None),
    'int8':     ('i', 4, "%s / 8.0",    "int(%s * 8)"),
    'int32':    ('i', 4, "%s / 32.0",   "int(%s * 32)"),
    'byte32':   ('b', 1, "%s / 32.0",   "int(%s * 32)"),
}
def make_packet_type(pkt_id, pkt_name, desc):
    def parse_fields():
        for line in desc.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            yield PROTOCOL_LINE(line).groups()

    class Codegen(object):
        def __init__(self):
            self._code = []
            self._depth = 0
        def add(self, line):
            self._code.append("%s%s" % (" " * (self._depth * 2), line))
        def indent(self):
            self._depth += 1
        def dedent(self):
            self._depth -= 1
        def get(self):
            return "\n".join(self._code)

    def primitives_optimizer(fields):
        parts = []
        run, run_size = [], 0
        for name, parser, condition in fields:
            if OPTIMIZE and parser in PRIMITIVES and not condition:
                primitive, size, read_mod, write_mod = PRIMITIVES[parser]
                run.append((name, primitive, read_mod, write_mod))
                run_size += size
            elif run:
                names, primitives, read_mods, write_mods = izip(*run)
                fmt = ">%s" % "".join(primitive for primitive in primitives)
                parts.append((True, (fmt, run_size, names, read_mods, write_mods)))
                run, run_size = [], 0
                parts.append((False, (name, parser, condition)))
            else:
                parts.append((False, (name, parser, condition)))
        if run:
            names, primitives, read_mods, write_mods = izip(*run)
            fmt = ">%s" % "".join(primitive for primitive in primitives)
            parts.append((True, (fmt, run_size, names, read_mods, write_mods)))
        return parts

    fields = list(parse_fields())
    optimized = primitives_optimizer(fields)

    code = Codegen()

    for run_idx, (is_optimized, info) in enumerate(optimized):
        if is_optimized:
            fmt, size, names, read_mods, _ = info
            code.add("_tmp = Struct('%s')" % fmt)
            code.add("_RUN_%d_PACK, _RUN_%d_UNPACK = _tmp.pack, _tmp.unpack" % (
                run_idx, run_idx))

    code.add("class %s(object):" % pkt_name) 
    code.indent()
    if fields:
        code.add("__slots__ = %s" % (
            ", ".join('"%s"' % name for name, parser, condition in fields)))
    code.add("id = %s" % pkt_id)

    code.add("@classmethod")
    signature = ["cls"]
    signature.extend(
        ("%s=None" if condition else "%s") % name 
        for name, parser, condition in fields
    )
    code.add("def create(%s):" % ", ".join(signature))
    code.indent()
    code.add("self = cls()")
    for name, parser, condition in fields:
        code.add("self.%s = %s" % (name, name))
    if not fields:
        code.add("pass")
    code.add("return self")
    code.dedent()

    code.add("@classmethod")
    code.add("def parse(cls, b):")
    code.indent()
    code.add("self = cls()")
    for run_idx, (is_optimized, info) in enumerate(optimized):
        if is_optimized:
            fmt, size, names, read_mods, _ = info
            code.add("(%s,) = _RUN_%d_UNPACK(b.read(%d))" % (
                ", ".join("self.%s" % name for name in names),
                run_idx,
                size
            ))
            for name, mod in izip(names, read_mods):
                if mod:
                    code.add("self.%s = %s" % (
                        name, 
                        mod % ("self.%s" % name)
                    ))
        else:
            name, parser, condition = info
            if condition:
                code.add("if %s:" % condition)
                code.add("  self.%s = read_%s(b)" % (name, parser))
                code.add("else:")
                code.add("  self.%s = None" % name)
            else:
                code.add("self.%s = read_%s(b)" % (name, parser))

    if DEBUG_PKTS:
        code.add("remaining = len(b.read())")
        code.add("if remaining:")
        code.add("  print '-----> %d unread bytes in 0x%02x' % (remaining, self.id)")
        code.add("  assert False")
    code.add("return self")
    code.dedent()

    code.add("def emit(self, b):")
    code.indent()
    for run_idx, (is_optimized, info) in enumerate(optimized):
        if is_optimized:
            fmt, size, names, _, write_mods = info
            emit_names = []
            for name, mod in izip(names, write_mods):
                if mod:
                    code.add("%s = %s" % (
                        name, 
                        mod % ("self.%s" % name)
                    ))
                    emit_names.append(name)
                else:
                    emit_names.append("self.%s" % name)
            code.add("b.write(_RUN_%d_PACK(%s))" % (
                run_idx,
                ", ".join(emit_names)
            ))
        else:
            name, parser, condition = info
            if condition:
                code.add("if %s:" % condition)
                code.add("  write_%s(b, self.%s)" % (parser, name))
            else:
                code.add("write_%s(b, self.%s)" % (parser, name))
    if not optimized:
        code.add("pass")
    code.dedent()

    code.add("@classmethod")
    code.add("def desc(cls):")
    code.indent()
    code.add("out = []")
    code.add("out.append('%s (0x%02x)')" % (pkt_name, pkt_id))
    for name, parser, condition in fields:
        code.add("out.append('  %s (%s)')" % (name, parser))
    code.add("return '\\n'.join(out)")
    code.dedent()

    code.add("def __str__(self):")
    code.indent()
    code.add("out = []")
    code.add("out.append('%s (0x%02x)')" % (pkt_name, pkt_id))
    for name, parser, condition in fields:
        code.add("out.append('  %s: %%r (%s)' %% (self.%s,))" % (name, parser, name))
    code.add("return '\\n'.join(out)")

    if DEBUG_PKTS:
        print "-------------------------"
        print "\n".join("%3d %s" % (num+1, line) 
            for num, line in enumerate(code.get().split("\n")))
        print

    compiled = compile(code.get(), "%s:%s" % (__file__, pkt_name), 'exec')

    env = {
        'Struct': Struct
    }
    for run_idx, (is_optimized, info) in enumerate(optimized):
        if not is_optimized:
            name, parser, condition = info
            for mode in ('read', 'write'):
                env['%s_%s' % (mode, parser)] = globals()['%s_%s' % (mode, parser)]

    exec compiled in env
    return env[pkt_name]


ProtocolVersion = {}


def protocol(protocol_version):
    if not protocol_version in ProtocolVersion:
        ProtocolVersion[protocol_version] = Protocol(protocol_version)
    return ProtocolVersion[protocol_version]


class Protocol(object):
    def __init__(self, protocol_version):
        self._protocol_version = protocol_version
        self._name = None
        self._states = {} # state, side, pkt_id

    def based_on(self, other_protocol_version):
        other_protocol = ProtocolVersion[other_protocol_version]
        for state, sides in other_protocol._states.iteritems():
            for side, packets in enumerate(sides):
                for packet in packets.itervalues():
                    self.add_packet(state, side, packet)

    def set_name(self, name):
        self._name = name

    @property
    def version(self):
        return self._protocol_version

    @property
    def name(self):
        return self._name

    def get_packets(self, state, side):
        return self._states[state][side]

    def add_packet(self, state, side, packet):
        # log.debug("adding state %d, side %d, packet %d to protocol %d" % (
        #     state, side, packet.id, self._protocol_version))
        self._states.setdefault(state, [{}, {}])[side][packet.id] = packet
        name = "%s%s%s" % (STATES[state], SIDES[side], packet.__name__)
        setattr(self, name, packet)

    def state(self, state):
        return _State(self, state)

    def __str__(self):
        return "# protocol %d (%s)\n\n%s\n" % (
            self._protocol_version, self._name,
            "\n".join("- STATE %s:\n=================\n\n%s" % (
                STATES[state], 
                "\n".join("  %s:\n  ---------------\n\n%s\n" % (
                    SIDES[side],
                    "\n".join("+ %s\n" % (
                        packet.desc()
                    ) for packet in packets.itervalues())
                ) for side, packets in enumerate(sides))
            ) for state, sides in self._states.iteritems()))


class _State(object):
    def __init__(self, protocol, state):
        self._protocol = protocol
        self._state = state

    @property
    def from_server(self):
        return _Side(self._protocol, self._state, 0).__call__

    @property
    def from_client(self):
        return _Side(self._protocol, self._state, 1).__call__


class _Side(object):
    def __init__(self, protocol, state, side):
        self._protocol = protocol
        self._state = state
        self._side = side

    def __call__(self, pkt_id, pkt_name, desc=""):
        self._protocol.add_packet(self._state, self._side, 
            make_packet_type(pkt_id, pkt_name, desc))


class Endpoint(object):
    @classmethod
    def client_pair(cls, protocol_version):
        return cls.from_server(protocol_version), cls.to_server(protocol_version)

    @classmethod
    def server_pair(cls, protocol_version):
        return cls.from_client(protocol_version), cls.to_client(protocol_version)

    @classmethod
    def from_server(cls, protocol_version):
        return cls(protocol_version, CLIENTBOUND)

    @classmethod
    def from_client(cls, protocol_version):
        return cls(protocol_version, SERVERBOUND)

    to_client = from_server 
    to_server = from_client

    def __init__(self, protocol_version, side):
        self._side = side
        self._protocol = ProtocolVersion[protocol_version]
        self.switch_state(HANDSHAKE)

    @property
    def protocol(self):
        return self._protocol

    @property
    def state(self):
        return self._state

    def switch_state(self, state):
        self._state = state
        self._state_packets = self._protocol.get_packets(state, self._side)
        log.debug("endpoint switch to state %d" % (self._state))

    def read(self, buf):
        raw = read_raw(buf)
        if raw is None:
            return None, None
        pkt_id = read_varint(raw)
        # log.debug("received pkt id %d in state %d" % (pkt_id, self._state))
        return self._state_packets[pkt_id].parse(raw), raw

    def write(self, buf, pkt_id, **data):
        # log.debug("sending pkt id %d %r" % (pkt_id, data))
        write_packet(buf, self._state_packets[pkt_id].create(**data))


class MinecraftSocket(object):
    def __init__(self, sock):
        self._sock = sock
        self._sock_send = sock.sendall
        self._sock_recv = sock.recv
        self._encrypt = None
        self._decrypt = None

        self._sent = 0
        self._received = 0

    def set_cipher(self, send_cipher, recv_cipher):
        self._encrypt = send_cipher.encrypt
        self._decrypt = recv_cipher.decrypt
        log.debug("set send/recv cipher")

    def send(self, buf):
        data = buf.getvalue()
        if self._encrypt:
            data = self._encrypt(data)
        self._sock_send(data)
        self._sent += len(data)

    def recv(self):
        data = self._sock_recv(4096)
        if not data:
            return ""
        if self._decrypt:
            data = self._decrypt(data)
        self._received += len(data)
        return data

    def close(self):
        self._sock.close()


CLIENTBOUND = 0
SERVERBOUND = 1

SIDES = "Clientbound", "Serverbound"

HANDSHAKE = 0
STATUS = 1
LOGIN = 2
PLAY = 3

STATES = "Handshake", "Status", "Login", "Play"

protocol(0).set_name("13w42a")

############################################### Handshake
protocol(0).state(HANDSHAKE).from_client(0x00, "Handshake", """
    version         varint
    addr            string 
    port            ushort
    state           varint
""")

############################################### Status
protocol(0).state(STATUS).from_server(0x00, "Response", """
    response        json
""")
protocol(0).state(STATUS).from_server(0x01, "Ping", """
    time            long
""")
#---------------------------------------------------
protocol(0).state(STATUS).from_client(0x00, "Request")
protocol(0).state(STATUS).from_client(0x01, "Ping", """
    time            long
""")

############################################### Login
protocol(0).state(LOGIN).from_server(0x00, "Disconnect", """
    reason          json
""")
protocol(0).state(LOGIN).from_server(0x01, "EncryptionRequest", """
    server_id       string
    public_key      short_byte_array
    challenge_token short_byte_array
""")
protocol(0).state(LOGIN).from_server(0x02, "LoginSuccess", """
    uuid            string
    username        string
""")
#---------------------------------------------------
protocol(0).state(LOGIN).from_client(0x00, "LoginStart", """
    name            string
""")
protocol(0).state(LOGIN).from_client(0x01, "EncryptionResponse", """
    shared_secret   short_byte_array
    response_token  short_byte_array
""")

############################################### Play
protocol(0).state(PLAY).from_server(0x00, "KeepAlive", """
    keepalive_id    int 
""")
protocol(0).state(PLAY).from_server(0x01, "JoinGame", """
    eid             int
    game_mode       ubyte
    dimension       byte
    difficulty      ubyte
    max_players     ubyte
    level_type      string
""")
protocol(0).state(PLAY).from_server(0x02, "ChatMesage", """
    chat            json
""")
protocol(0).state(PLAY).from_server(0x03, "TimeUpdate", """
    world_age       long
    time_of_day     long
""")
protocol(0).state(PLAY).from_server(0x04, "EntityEquipment", """
    eid             int
    slot            short
    item            slot
""")
protocol(0).state(PLAY).from_server(0x05, "SpawnPosition", """
    x               int
    y               int
    z               int
""")
protocol(0).state(PLAY).from_server(0x06, "HealthUpdate", """
    health          float
    food            short
    food_saturation float
""")
protocol(0).state(PLAY).from_server(0x07, "Respawn", """
    dimension       int
    difficulty      ubyte
    game_mode       ubyte
    level_type      string
""")
protocol(0).state(PLAY).from_server(0x08, "PlayerPositionAndLook", """
    x               double
    y               double
    z               double
    yaw             float
    pitch           float
    on_ground       bool
""")
protocol(0).state(PLAY).from_server(0x09, "HeldItemChange", """
    slot            byte
""")
protocol(0).state(PLAY).from_server(0x0a, "UseBed", """
    eid             int
    x               int
    y               byte
    z               int
""")
protocol(0).state(PLAY).from_server(0x0b, "Animation", """
    eid             varint
    animation       ubyte
""")
protocol(0).state(PLAY).from_server(0x0c, "SpawnPlayer", """
    eid             varint
    uuid            string
    name            string
    x               int32
    y               int32
    z               int32
    yaw             ubyte
    pitch           ubyte
    current_item    short
    metadata        metadata
""")
protocol(0).state(PLAY).from_server(0x0d, "CollectItem", """
    collected_eid   int
    collector_eid   int
""")
protocol(0).state(PLAY).from_server(0x0e, "SpawnObject", """
    eid             varint
    type            byte
    x               int32
    y               int32
    z               int32
    pitch           ubyte
    yaw             ubyte
    data            objdata
""")
protocol(0).state(PLAY).from_server(0x0f, "SpawnMob", """
    eid             varint
    type            ubyte
    x               int32
    y               int32
    z               int32
    pitch           ubyte
    head_pitch      ubyte
    yaw             ubyte
    velocity_x      short
    velocity_y      short
    velocity_z      short
    metadata        metadata
""")
protocol(0).state(PLAY).from_server(0x10, "SpawnPainting", """
    eid             varint
    title           string
    x               int
    y               int
    z               int
    direction       int
""")
protocol(0).state(PLAY).from_server(0x11, "SpawnExperienceOrb", """
    eid             varint
    x               int32
    y               int32
    z               int32
    count           short
""")
protocol(0).state(PLAY).from_server(0x12, "EntityVelocity", """
    eid             int
    velocity_x      short
    velocity_y      short
    velocity_z      short
""")
protocol(0).state(PLAY).from_server(0x13, "DestroyEntities", """
    eids            byte_int_array
""")
protocol(0).state(PLAY).from_server(0x14, "Entity", """
    eid             int
""")
protocol(0).state(PLAY).from_server(0x15, "EntityRelativeMove", """
    eid             int
    dx              byte32
    dy              byte32
    dz              byte32
""")
protocol(0).state(PLAY).from_server(0x16, "EntityLook", """
    eid             int
    yaw             ubyte
    pitch           ubyte
""")
protocol(0).state(PLAY).from_server(0x17, "EntityLookAndRelativeMove", """
    eid             int
    dx              byte32
    dy              byte32
    dz              byte32
    yaw             ubyte
    pitch           ubyte
""")
protocol(0).state(PLAY).from_server(0x18, "EntityTeleport", """
    eid             int
    x               int32
    y               int32
    z               int32
    yaw             ubyte
    pitch           ubyte
""")
protocol(0).state(PLAY).from_server(0x19, "EntityHeadLook", """
    eid             int
    head_yaw        ubyte
""")
protocol(0).state(PLAY).from_server(0x1a, "EntityStatus", """
    eid             int
    status          byte
""")
protocol(0).state(PLAY).from_server(0x1b, "AttachEntity", """
    eid             int
    vehicle_id      int
    leash           bool
""")
protocol(0).state(PLAY).from_server(0x1c, "EntityMetadata", """
    eid             int
    metadata        metadata
""")
protocol(0).state(PLAY).from_server(0x1d, "EntityEffect", """
    eid             int
    effect_id       byte
    amplifier       byte
    duration        short
""")
protocol(0).state(PLAY).from_server(0x1e, "RemoveEntityEffect", """
    eid             int
    effect_id       byte
""")
protocol(0).state(PLAY).from_server(0x1f, "SetExperience", """
    bar             float
    level           short
    total_exp       short
""")
protocol(0).state(PLAY).from_server(0x20, "EntityProperty", """
    eid             int
    properties      property_array
""")
protocol(0).state(PLAY).from_server(0x21, "ChunkData", """
    chunk_x         int
    chunk_z         int
    continuous      bool
    chunk_bitmap    ushort
    add_bitmap      ushort
    compressed      int_byte_array
""")
protocol(0).state(PLAY).from_server(0x22, "MultiBlockChange", """
    chunk_x         varint
    chunk_z         varint
    changes         changes
""")
protocol(0).state(PLAY).from_server(0x23, "BlockChange", """
    x               int
    y               ubyte
    z               int
    block_type      varint
    block_data      ubyte
""")
protocol(0).state(PLAY).from_server(0x24, "BlockAction", """
    x               int
    y               short
    z               int
    b1              ubyte
    b2              ubyte
    block_type      varint
""")
protocol(0).state(PLAY).from_server(0x25, "BlockBreakAnimation", """
    eid             varint
    x               int
    y               int
    z               int
    destroy_stage   byte
""")
protocol(0).state(PLAY).from_server(0x26, "MapChunkBulk", """
    bulk            map_chunk_bulk
""")
protocol(0).state(PLAY).from_server(0x27, "Explosion", """
    x               float
    y               float
    z               float
    radius          float
    records         explosions
    motion_x        float
    motion_y        float
    motion_z        float
""")
protocol(0).state(PLAY).from_server(0x28, "Effect", """
    effect_id       int
    x               int
    y               byte
    z               int
    data            int
    constant_volume bool
""")
protocol(0).state(PLAY).from_server(0x29, "SoundEffect", """
    sound           string
    x               int8
    y               int8
    z               int8
    volume          float
    pitch           ubyte
""")
protocol(0).state(PLAY).from_server(0x2a, "Particle", """
    particle        string
    x               float
    y               float
    z               float
    offset_x        float
    offset_y        float
    offset_z        float
    speed           float
    number          int
""")
protocol(0).state(PLAY).from_server(0x2b, "ChangeGameState", """
    reason          ubyte
    value           float
""")
protocol(0).state(PLAY).from_server(0x2c, "SpawnGlobalEntity", """
    eid             varint
    type            byte
    x               int
    y               int
    z               int
""")
protocol(0).state(PLAY).from_server(0x2d, "OpenWindow", """
    window_id       ubyte
    type            ubyte
    title           string
    slot_count      ubyte
    use_title       bool
    eid             int                 self.type == 11
""")
protocol(0).state(PLAY).from_server(0x2e, "CloseWindow", """
    window_id       ubyte
""")
protocol(0).state(PLAY).from_server(0x2f, "SetSlot", """
    window_id       ubyte
    slot            short
    item            slot
""")
protocol(0).state(PLAY).from_server(0x30, "WindowItem", """
    window_id       ubyte
    slots           slot_array
""")
protocol(0).state(PLAY).from_server(0x31, "WindowProperty", """
    window_id       ubyte
    property        short
    value           short
""")
protocol(0).state(PLAY).from_server(0x32, "ConfirmTransaction", """
    window_id       ubyte
    action_num      short
    accepted        bool
""")
protocol(0).state(PLAY).from_server(0x33, "UpdateSign", """
    x               int
    y               short
    z               int
    line1           string
    line2           string
    line3           string
    line4           string
""")
protocol(0).state(PLAY).from_server(0x34, "Maps", """
    map_id          varint
    data            short_byte_array
""")
protocol(0).state(PLAY).from_server(0x35, "UpdateBlockEntity", """
    x               int
    y               short
    z               int
    action          ubyte
    nbt             short_byte_array
""")
protocol(0).state(PLAY).from_server(0x36, "SignEditorOpen", """
    x               int
    y               int
    z               int
""")
protocol(0).state(PLAY).from_server(0x37, "Statistics", """
    stats           statistic_array
""")
protocol(0).state(PLAY).from_server(0x38, "PlayerListItem", """
    name            string
    online          bool
    ping            short
""")
protocol(0).state(PLAY).from_server(0x39, "PlayerAbility", """
    flags           byte
    flying_speed    float
    walking_speed   float
""")
protocol(0).state(PLAY).from_server(0x3a, "TabComplete", """
    completions     varint_string_array
""")
protocol(0).state(PLAY).from_server(0x3b, "ScoreboardObjective", """
    name            string
    value           string
    operation       byte
""")
protocol(0).state(PLAY).from_server(0x3c, "UpdateScore", """
    name            string
    remove          byte
    score_name      string              self.remove != 1
    value           int                 self.remove != 1
""")
protocol(0).state(PLAY).from_server(0x3d, "DisplayScoreboard", """
    position        byte
    score_name      string
""")
protocol(0).state(PLAY).from_server(0x3e, "Teams", """
    team_name       string
    mode            byte
    display_name    string              self.mode == 0 or self.mode == 2
    prefix          string              self.mode == 0 or self.mode == 2
    suffix          string              self.mode == 0 or self.mode == 2
    friendly_fire   byte                self.mode == 0 or self.mode == 2
    players         short_string_array  self.mode in (0, 3, 4)
""")
protocol(0).state(PLAY).from_server(0x3f, "PluginMessage", """
    channel         string
    data            short_byte_array
""")
protocol(0).state(PLAY).from_server(0x40, "Disconnect", """
    reason          json
""")
#---------------------------------------------------
protocol(0).state(PLAY).from_client(0x00, "KeepAlive", """
    keepalive_id    int 
""")
protocol(0).state(PLAY).from_client(0x01, "ChatMessage", """
    chat            string
""")
protocol(0).state(PLAY).from_client(0x02, "UseEntity", """
    target          int
    button          byte
""")
protocol(0).state(PLAY).from_client(0x03, "Player", """
    on_ground       bool
""")
protocol(0).state(PLAY).from_client(0x04, "PlayerPosition", """
    x               double
    y               double
    stance          double
    z               double
    on_ground       bool
""")
protocol(0).state(PLAY).from_client(0x05, "PlayerLook", """
    yaw             float
    pitch           float
    on_ground       bool
""")
protocol(0).state(PLAY).from_client(0x06, "PlayerPositionAndLook", """
    x               double
    y               double
    stance          double
    z               double
    yaw             float
    pitch           float
    on_ground       bool
""")
protocol(0).state(PLAY).from_client(0x07, "PlayerDigging", """
    status          byte
    x               int
    y               ubyte
    z               int
    face            byte
""")
protocol(0).state(PLAY).from_client(0x08, "BlockPlacement", """
    x               int
    y               ubyte
    z               int
    direction       byte
    held_item       slot
    cursor_x        byte
    cursor_y        byte
    cursor_z        byte
""")
protocol(0).state(PLAY).from_client(0x09, "HeldItemChange", """
    slot            short
""")
protocol(0).state(PLAY).from_client(0x0a, "Animation", """
    eid             int
    animation       ubyte
""")
protocol(0).state(PLAY).from_client(0x0b, "EntityAction", """
    eid             int
    action_id       byte
    jump_boost      int
""")
protocol(0).state(PLAY).from_client(0x0c, "SteerVehicle", """
    sideways        float
    forward         float
    jump            bool
    unmount         bool
""")
protocol(0).state(PLAY).from_client(0x0d, "CloseWindow", """
    window_id       byte
""")
protocol(0).state(PLAY).from_client(0x0e, "ClickWindow", """
    window_id       byte
    slot            short
    button          byte
    action_num      short
    mode            byte
    clicked_item    slot
""")
protocol(0).state(PLAY).from_client(0x0f, "ConfirmTransaction", """
    window_id       ubyte
    action_num      short
    accepted        bool
""")
protocol(0).state(PLAY).from_client(0x10, "CreativeInventoryAction", """
    slot            short
    clicked_item    slot
""")
protocol(0).state(PLAY).from_client(0x11, "EnchantItem", """
    window_id       ubyte
    enchantment     byte
""")
protocol(0).state(PLAY).from_client(0x12, "UpdateSign", """
    x               int
    y               short
    z               int
    line1           string
    line2           string
    line3           string
    line4           string
""")
protocol(0).state(PLAY).from_client(0x13, "PlayerAbilities", """
    flags           byte
    flying_speed    float
    walking_speed   float
""")
protocol(0).state(PLAY).from_client(0x14, "TabComplete", """
    text            string
""")
protocol(0).state(PLAY).from_client(0x15, "ClientSettings", """
    locale          string
    view_distance   byte
    chat_flags      byte
    unused          bool
    difficulty      byte
    show_cape       bool
""")
protocol(0).state(PLAY).from_client(0x16, "ClientStatus", """
    action_id       byte
""")
protocol(0).state(PLAY).from_client(0x17, "PluginMessage", """
    channel         string
    data            short_byte_array
""")

protocol(1).set_name("13w42b")
protocol(1).based_on(0)

protocol(2).set_name("13w43a")
protocol(2).based_on(1)

protocol(3).set_name("1.7.1")
protocol(3).based_on(2)

protocol(4).set_name("1.7.2")
protocol(4).based_on(3)
protocol(4).state(PLAY).from_server(0x22, "MultiBlockChange", """
    chunk_x         int
    chunk_z         int
    changes         changes
""")
