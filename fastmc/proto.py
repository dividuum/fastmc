# -*- coding: utf-8 -*-
#
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
import os
import logging

from array import array
from struct import pack, unpack, Struct
from collections import namedtuple
from cStringIO import StringIO
from itertools import izip
from simplejson import loads as json_loads, dumps as json_dumps

log = logging.getLogger(__name__)

OPTIMIZE = not bool(os.getenv("FASTMC_NO_OPTIMIZE"))
DEBUG_PARSER = bool(os.getenv("FASTMC_DEBUG_PARSER"))
DEBUG_PACKET = bool(os.getenv("FASTMC_DEBUG_PACKET"))

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

Position = namedtuple("Position", "x y z")

def read_position(b):
    x = read_int(b)
    y = read_ubyte(b)
    z = read_int(b)
    return Position(x, y, z)
def write_position(b, pos):
    write_int(b, pos.x)
    write_ubyte(b, pos.y)
    write_int(b, pos.z)

def read_position_packed(b):
    # most retarded protocol encoding ever to save
    # a few bytes in a data type that's rarly used.
    p = read_ulong(b)
    def twentysix_bit_2_complement(v):
        if v & 0x2000000:
            v = v - (1 << 26)
        return v
    return Position(
        twentysix_bit_2_complement(p >> 38), 
        (p >> 26) & 0xfff, 
        twentysix_bit_2_complement(p & 0x3ffffff)
    )
def write_position_packed(b, pos):
    write_ulong(b, (pos.x & 0x3ffffff) << 38 | pos.y << 26 | pos.z & 0x3ffffff)

def read_short_string(b):
    size = read_short(b)
    string = b.read(size)
    return string.decode("utf8")
def write_short_string(b, string):
    encoded = string.encode("utf8")
    write_short(b, len(encoded))
    b.write(encoded)

def read_string(b):
    size = read_varint(b)
    string = b.read(size)
    return string.decode("utf8")
def write_string(b, string):
    encoded = string.encode("utf8")
    write_varint(b, len(encoded))
    b.write(encoded)

def read_bytes_exhaustive(b):
    # ugly hack for plugin message in protocol version 47:
    # The value doesn't have a size prefix, so you have to
    # to read all remaining bytes here. *barf*
    return b.read(10000000000)
def write_bytes_exhaustive(b, string):
    b.write(string)

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
    write_int(b, int(value * 8))

def read_int32(b):
    return read_int(b) / 32.0
def write_int32(b, value):
    write_int(b, int(value * 32))

def read_byte32(b):
    return read_byte(b) / 32.0
def write_byte32(b, value):
    write_byte(b, int(value * 32))

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

def read_varint_byte_array(b):
    size = read_varint(b)
    return b.read(size)
def write_varint_byte_array(b, value):
    write_varint(b, len(value))
    b.write(value)

PlayerData = namedtuple("PlayerData", "name value signature")
def read_player_data(b):
    return PlayerData(
        read_string(b),
        read_string(b),
        read_string(b),
    )
def write_player_data(b, pd):
    write_string(b, pd.name)
    write_string(b, pd.value)
    write_string(b, pd.signature)

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
read_int_varint_array = make_array_reader(read_int, read_varint)
write_int_varint_array = make_array_writer(write_int, write_varint)
read_varint_varint_array = make_array_reader(read_varint, read_varint)
write_varint_varint_array = make_array_writer(write_varint, write_varint)
read_short_int_array = make_array_reader(read_short, read_int)
write_short_int_array = make_array_writer(write_short, write_int)
read_int_string_array = make_array_reader(read_int, read_string)
write_int_string_array = make_array_writer(write_int, write_string)
read_short_string_array = make_array_reader(read_short, read_string)
write_short_string_array = make_array_writer(write_short, write_string)
read_varint_string_array = make_array_reader(read_varint, read_string)
write_varint_string_array = make_array_writer(write_varint, write_string)
read_varint_player_data_array = make_array_reader(read_varint, read_player_data)
write_varint_player_data_array = make_array_writer(write_varint, write_player_data)

Slot = namedtuple("Slot", "item_id count damage nbt")
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

read_slot_array = make_array_reader(read_short, read_slot)
write_slot_array = make_array_writer(write_short, write_slot)

def read_slot_1_8(b):
    item_id = read_short(b)
    if item_id == -1:
        return None
    count = read_byte(b) 
    damage = read_short(b)
    name, nbt = read_nbt(b)
    if nbt.tag_type == NbtTag.END:
        nbt = None
    return Slot(item_id, count, damage, nbt)
def write_slot_1_8(b, slot):
    if slot is None:
        write_short(b, -1)
        return
    write_short(b, slot.item_id)
    write_byte(b, slot.count)
    write_short(b, slot.damage)
    if slot.nbt is None:
        write_byte(b, 0)
    else:
        write_nbt(b, NBT('', slot.nbt))

read_slot_array_1_8 = make_array_reader(read_short, read_slot_1_8)
write_slot_array_1_8 = make_array_writer(write_short, write_slot_1_8)

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

BlockChange = namedtuple("BlockChange", "x y z block_id")
def read_changes_14w26c(b):
    def read_change(b):
        coords = read_ushort(b)
        block_id = read_varint(b)
        return BlockChange(
            (coords >> 12) & 0xF,
            coords & 0xFF,
            (coords >>  8) & 0xF,
            block_id,
        )
    count = read_varint(b)
    return [read_change(b) for _ in xrange(count)]
def write_changes_14w26c(b, changes):
    def write_change(b, change):
        write_ushort(b, change.y | change.z << 8 | change.x << 12)
        write_varint(b, change.block_id)
    write_varint(b, len(changes))
    for change in changes:
        write_change(b, change)

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

Rotation = namedtuple("Rotation", "pitch roll yaw")
def read_rotation(b):
    pitch = read_float(b)
    roll = read_float(b)
    yaw = read_float(b)
    return Rotation(pitch, roll, yaw)
def write_rotation(b, value):
    write_float(b, value.pitch)
    write_float(b, value.roll)
    write_float(b, value.yaw)

def make_metadata_pair(readers, writers):
    def read_metadata(b):
        meta = {}
        while 1:
            item = read_ubyte(b)
            if item == 0x7f:
                return meta
            meta_type = item >> 5
            meta[item & 0x1f] = meta_type, readers[meta_type](b)
    def write_metadata(b, meta):
        for index, (meta_type, meta_value) in meta.iteritems():
            write_ubyte(b, meta_type << 5 | index & 0x1f)
            writers[meta_type](b, meta_value)
        write_ubyte(b, 0x7f)
    return read_metadata, write_metadata

META_READERS = {
    0: read_byte,
    1: read_short,
    2: read_int,
    3: read_float,
    4: read_string,
    5: read_slot,
    6: read_vector,
}
META_WRITERS = {
    0: write_byte,
    1: write_short,
    2: write_int,
    3: write_float,
    4: write_string,
    5: write_slot,
    6: write_vector,
}
read_metadata, write_metadata = make_metadata_pair(META_READERS, META_WRITERS)

META_READERS_1_8 = {
    0: read_byte,
    1: read_short,
    2: read_int,
    3: read_float,
    4: read_string,
    5: read_slot_1_8,
    6: read_vector,
    7: read_rotation,
}
META_WRITERS_1_8 = {
    0: write_byte,
    1: write_short,
    2: write_int,
    3: write_float,
    4: write_string,
    5: write_slot_1_8,
    6: write_vector,
    7: write_rotation,
}
read_metadata_1_8, write_metadata_1_8 = make_metadata_pair(META_READERS_1_8, META_WRITERS_1_8)

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

def read_property_array_14w04a(b):
    properties = {}
    num_properties = read_int(b)
    for _ in xrange(num_properties):
        key = read_string(b)
        value = read_double(b)
        num_modifiers = read_varint(b)
        modifiers = []
        for _ in xrange(num_modifiers):
            msl, lsl, amount, operation = unpack(">QQdb", b.read(25))
            modifiers.append(Modifier(msl << 64 | lsl, amount, operation))
        properties[key] = Property(value, modifiers)
    return properties
def write_property_array_14w04a(b, properties):
    write_int(b, len(properties))
    for key, property in properties.iteritems():
        write_string(b, key)
        write_double(b, property.value)
        write_varint(b, len(property.modifiers))
        for modifier in property.modifiers:
            b.write(pack(">QQdb", 
                modifier.uuid >> 64,
                modifier.uuid & 0xffffffffffffffff,
                modifier.amount,
                modifier.operation
            ))

def read_uuid(b):
    msl, lsl = unpack(">QQ", b.read(16))
    return msl << 64 | lsl
def write_uuid(b, uuid):
    b.write(pack(">QQ", uuid >> 64, uuid & 0xffffffffffffffff))

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

ChunkBulk14w28a = namedtuple("ChunkBulk14w28a", "sky_light_sent data chunks")
Chunk14w28a = namedtuple("Chunk14w28a", "x z primary_bitmap data_offset")
def read_map_chunk_bulk_14w28a(b):
    def count_bits(v):
        return bin(v).count("1") # yep
    sky_light_sent = read_bool(b)
    num_chunks = read_varint(b)
    chunks = []
    data_offset = 0
    for n in xrange(num_chunks):
        chunk_x = read_int(b)
        chunk_z = read_int(b)
        primary_bitmap = read_ushort(b)
        chunks.append(Chunk14w28a(chunk_x, chunk_z, primary_bitmap, data_offset))

        num_chunks = count_bits(primary_bitmap)
        data_offset += 16*16*16 * 2 * num_chunks      # block data
        data_offset += 16*16*16 / 2 * num_chunks      # block light
        if sky_light_sent:
            data_offset += 16*16*16 / 2 * num_chunks  # sky light
        data_offset += 16*16                          # biome data

    data = b.read(data_offset)
    assert len(data) == data_offset
    return ChunkBulk14w28a(sky_light_sent, buffer(data, 0, data_offset), chunks)
def write_map_chunk_bulk_14w28a(b, bulk):
    write_bool(b, bulk.sky_light_sent)
    write_varint(b, len(bulk.chunks))
    for chunk in bulk.chunks:
        write_int(b, chunk.x)
        write_int(b, chunk.z)
        write_ushort(b, chunk.primary_bitmap)
    b.write(bulk.data)

MapIcon = namedtuple("MapIcon", "direction type x y")
def read_map_icons(b):
    def read_icon(b):
        dir_type = read_byte(b)
        x = read_byte(b)
        y = read_byte(b)
        return MapIcon(dir_type >> 4, dir_type & 0xF, x, y)
    num_icons = read_varint(b)
    icons = []
    for n in xrange(num_icons):
        icons.append(read_icon(b))
    return icons
def write_map_icons(b, icons):
    write_varint(b, len(icons))
    for icon in icons:
        write_byte(b, icon.direction << 4 | icon.type)
        write_byte(b, icon.x)
        write_byte(b, icon.y)

PlayerListActions = namedtuple("PlayerListAction", "action players")
LIST_ACTION_ADD_PLAYER = 0
PlayerListActionAdd = namedtuple("PlayerListActionAdd", "uuid name properties game_mode ping display_name")
PlayerListActionAddProperty = namedtuple("PlayerListActionAddProperty", "name value signature")

LIST_ACTION_UPDATE_GAMEMODE = 1
PlayerListActionGamemode = namedtuple("PlayerListActionGamemode", "uuid game_mode")

LIST_ACTION_UPDATE_LATENCY = 2
PlayerListActionLatency = namedtuple("PlayerListActionLatency", "uuid ping")

LIST_ACTION_UPDATE_DISPLAY_NAME = 3
PlayerListActionDisplayName = namedtuple("PlayerListActionDisplayName", "uuid display_name")

LIST_ACTION_REMOVE_PLAYER = 4
PlayerListActionRemove = namedtuple("PlayerListActionRemove", "uuid")

def read_list_actions(b):
    action = read_varint(b)
    num_players = read_varint(b)
    players = []
    for _ in xrange(num_players):
        uuid = read_uuid(b)
        if action == LIST_ACTION_ADD_PLAYER:
            name = read_string(b)
            num_properties = read_varint(b)
            properties = []
            for _ in xrange(num_properties):
                prop_name = read_string(b)
                prop_value = read_string(b)
                is_signed = read_bool(b)
                if is_signed:
                    prop_sig = read_string(b)
                else:
                    prop_sig = None
                properties.append(PlayerListActionAddProperty(
                    prop_name, prop_value, prop_sig
                ))
            game_mode = read_varint(b)
            ping = read_varint(b)
            has_display_name = read_bool(b)
            if has_display_name:
                display_name = read_json(b)
            else:
                display_name = None
            players.append(PlayerListActionAdd(
                uuid, name, properties, game_mode, ping, display_name
            ))
        elif action == LIST_ACTION_UPDATE_GAMEMODE:
            game_mode = read_varint(b)
            players.append(PlayerListActionGamemode(uuid, game_mode))
        elif action == LIST_ACTION_UPDATE_LATENCY:
            ping = read_varint(b)
            players.append(PlayerListActionLatency(uuid, ping))
        elif action == LIST_ACTION_UPDATE_DISPLAY_NAME:
            has_display_name = read_bool(b)
            if has_display_name:
                display_name = read_json(b)
            else:
                display_name = None
            players.append(PlayerListActionDisplayName(uuid, display_name))
        elif action == LIST_ACTION_REMOVE_PLAYER:
            players.append(PlayerListActionRemove(uuid))
        else:
            raise ValueError("invalid player list action")
    return PlayerListActions(action, players)
def write_list_actions(b, actions):
    write_varint(b, actions.action)
    write_varint(b, len(actions.players))
    for player in actions.players:
        write_uuid(b, player.uuid)
        if actions.action == LIST_ACTION_ADD_PLAYER:
            write_string(b, player.name)
            write_varint(b, len(player.properties))
            for property in player.properties:
                write_string(b, property.name)
                write_string(b, property.value)
                has_signature = property.signature is not None
                write_bool(b, has_signature)
                if has_signature:
                    write_string(b, property.signature)
            write_varint(b, player.game_mode)
            write_varint(b, player.ping)
            has_display_name = player.display_name is not None
            write_bool(b, has_display_name)
            if has_display_name:
                write_json(b, player.display_name)
        elif actions.action == LIST_ACTION_UPDATE_GAMEMODE:
            write_varint(b, player.game_mode)
        elif actions.action == LIST_ACTION_UPDATE_LATENCY:
            write_varint(b, player.ping)
        elif actions.action == LIST_ACTION_UPDATE_DISPLAY_NAME:
            has_display_name = player.display_name is not None
            write_bool(b, has_display_name)
            if has_display_name:
                write_json(b, player.display_name)
        elif actions.action == LIST_ACTION_REMOVE_PLAYER:
            pass
        else:
            raise ValueError("invalid player list action")

class NbtTag(namedtuple('NbtTag', 'tag_type value')):
    END = 0
    BYTE = 1
    SHORT = 2
    INT = 3
    LONG = 4
    FLOAT = 5
    DOUBLE = 6
    BYTE_ARRAY = 7
    STRING = 8
    LIST = 9
    COMPOUND = 10
    INT_ARRAY = 11
NbtList = namedtuple('NbtList', 'tag_type values')
NBT = namedtuple('NBT', 'name root')

def read_nbt(b):
    def read_nbt_byte_array(b):
        length = read_int(b)
        return array('b', unpack(">%db" % length, b.read(length)))
    def read_nbt_int_array(b):
        length = read_int(b)
        return array('i', unpack(">%di" % length, b.read(length * 4)))
    def read_nbt_list(b):
        tag_type = read_byte(b)
        decoder = TAG_TYPES[tag_type]
        length = read_int(b)
        return NbtList(tag_type, [decoder(b) for _ in xrange(length)])
    def read_nbt_compound(b):
        out = {}
        while 1:
            name, nbt_tag = read_nbt_tag(b)
            if nbt_tag.tag_type == NbtTag.END:
                break
            out[name] = nbt_tag
        return out
    def read_nbt_tag(b):
        tag_type = read_byte(b)
        if tag_type == NbtTag.END:
            name = ""
            value = None
        else:
            name = read_short_string(b)
            value = TAG_TYPES[tag_type](b)
        return name, NbtTag(tag_type, value)
    TAG_TYPES = {
        NbtTag.END: lambda b: None,
        NbtTag.BYTE: read_byte,
        NbtTag.SHORT: read_short,
        NbtTag.INT: read_int,
        NbtTag.LONG: read_long,
        NbtTag.FLOAT: read_float,
        NbtTag.DOUBLE: read_double,
        NbtTag.BYTE_ARRAY: read_nbt_byte_array,
        NbtTag.STRING: read_short_string,
        NbtTag.LIST: read_nbt_list,
        NbtTag.COMPOUND: read_nbt_compound,
        NbtTag.INT_ARRAY: read_nbt_int_array,
    }
    name, nbt_tag = read_nbt_tag(b)
    # assert nbt_tag.tag_type == NbtTag.COMPOUND
    return NBT(name, nbt_tag)

def write_nbt(b, nbt):
    def write_nbt_byte_array(b, values):
        write_int(b, len(values))
        b.write(pack(">%db" % len(values), *values))
    def write_nbt_int_array(b, values):
        write_int(b, len(values))
        b.write(pack(">%di" % len(values), *values))
    def write_nbt_list(b, nbt_list):
        write_byte(b, nbt_list.tag_type)
        write_int(b, len(nbt_list.values))
        encoder = TAG_TYPES[nbt_list.tag_type]
        for value in nbt_list.values:
            encoder(b, value)
    def write_nbt_compound(b, values):
        for name, nbt_tag in values.iteritems():
            write_nbt_tag(b, name, nbt_tag)
        write_byte(b, NbtTag.END)
    def write_nbt_tag(b, name, nbt_tag):
        assert nbt_tag.tag_type != NbtTag.END
        write_byte(b, nbt_tag.tag_type)
        write_short_string(b, name)
        TAG_TYPES[nbt_tag.tag_type](b, nbt_tag.value)
    TAG_TYPES = {
        NbtTag.BYTE: write_byte,
        NbtTag.SHORT: write_short,
        NbtTag.INT: write_int,
        NbtTag.LONG: write_long,
        NbtTag.FLOAT: write_float,
        NbtTag.DOUBLE: write_double,
        NbtTag.BYTE_ARRAY: write_nbt_byte_array,
        NbtTag.STRING: write_short_string,
        NbtTag.LIST: write_nbt_list,
        NbtTag.COMPOUND: write_nbt_compound,
        NbtTag.INT_ARRAY: write_nbt_int_array,
    }
    write_nbt_tag(b, nbt.name, nbt.root)

def read_raw(b, compression_threshold):
    ss = b.snapshot()
    pkt_size = read_varint(b)
    if pkt_size is None:
        b.restore(ss)
        return None

    if compression_threshold is not None:
        data_length = read_varint(b)
        if data_length is None:
            b.restore(ss)
            return None

        data_size = pkt_size - size_varint(data_length)
        data = b.read(data_size)
        if len(data) != data_size:
            b.restore(ss)
            return None

        if data_length == 0: # uncompressed
            if len(data) >= compression_threshold:
                raise ValueError("packet is uncompressed despite being larger than %d" % compression_threshold)
            return StringIO(data)
        else:
            decompressed = data.decode('zlib')
            if len(decompressed) != data_length:
                raise ValueError("decompressed length doesn't match server values")
            if len(decompressed) < compression_threshold:
                raise ValueError("packet was compressed but data was smaller than %d" % compression_threshold)
            return StringIO(decompressed)
    else:
        data = b.read(pkt_size)
        if len(data) != pkt_size:
            b.restore(ss)
            return None
        return StringIO(data)

def write_packet(b, pkt, compression_threshold):
    raw = StringIO()
    write_varint(raw, pkt.id)
    pkt.emit(raw)
    size = raw.tell()
    if compression_threshold is None:
        write_varint(b, size)
        b.write(raw.getvalue())
    elif size >= compression_threshold:
        data = raw.getvalue()
        compressed = data.encode('zlib')
        write_varint(b, size_varint(len(data)) + len(compressed))
        write_varint(b, len(data))
        b.write(compressed)
    else:
        data = raw.getvalue()
        data_size = size_varint(0) + len(data)
        write_varint(b, data_size)
        write_varint(b, 0)
        b.write(data)

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
def make_packet_type(protocol_version, pkt_id, pkt_name, desc):
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

    if DEBUG_PACKET:
        code.add("remaining = len(b.read())")
        code.add("assert not remaining, 'WARNING: %d unread bytes in 0x%02x' % (remaining, self.id)")
        # code.add("  assert False")
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
        code.add("out.append('  %s (%s%s)')" % (name, parser, 
            " if %s" % condition if condition else ""))
    code.add("return '\\n'.join(out)")
    code.dedent()

    code.add("def __str__(self):")
    code.indent()
    code.add("out = []")
    code.add("out.append('%s (0x%02x)')" % (pkt_name, pkt_id))
    for name, parser, condition in fields:
        code.add("out.append('  %s: %%r (%s)' %% (self.%s,))" % (name, parser, name))
    code.add("return '\\n'.join(out)")

    if DEBUG_PARSER:
        print "--[ %s / protocol version %d ]-----------------------" % (pkt_name, protocol_version)
        print "\n".join("%3d %s" % (num+1, line) 
            for num, line in enumerate(code.get().split("\n")))
        print

    compiled = compile(code.get(), "%s:%s(0x%x)@%d" % (__file__, pkt_name, pkt_id, protocol_version), 'exec')

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
        return _Side(self._protocol, self._state, CLIENTBOUND).__call__

    @property
    def from_client(self):
        return _Side(self._protocol, self._state, SERVERBOUND).__call__


class _Side(object):
    def __init__(self, protocol, state, side):
        self._protocol = protocol
        self._state = state
        self._side = side

    def __call__(self, pkt_id, pkt_name, desc=""):
        self._protocol.add_packet(self._state, self._side, 
            make_packet_type(self._protocol.version, pkt_id, pkt_name, desc))


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
        self._compression_threshold = None
        self.switch_state(HANDSHAKE)

    @property
    def protocol(self):
        return self._protocol

    @property
    def state(self):
        return self._state

    def set_compression_threshold(self, compression_threshold):
        if compression_threshold == -1:
            compression_threshold = None
        self._compression_threshold = compression_threshold

    def switch_state(self, state):
        self._state = state
        self._state_packets = self._protocol.get_packets(state, self._side)
        log.debug("endpoint switch to state %d" % (self._state))

    def read(self, buf):
        raw = read_raw(buf, self._compression_threshold)
        if raw is None:
            return None, None
        pkt_id = read_varint(raw)
        # log.debug("received pkt id %d in state %d" % (pkt_id, self._state))
        return self._state_packets[pkt_id].parse(raw), raw

    def write(self, buf, pkt_id, **data):
        # log.debug("sending pkt id %d %r" % (pkt_id, data))
        self.write_pkt(buf, self._state_packets[pkt_id].create(**data))

    def write_pkt(self, buf, pkt):
        write_packet(buf, pkt, self._compression_threshold)

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
        # print "sending ", data
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

    def settimeout(self, timeout):
        self._sock.settimeout(timeout)

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
    x               int32
    y               int32
    z               int32
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
    window_id       ubyte
""")
protocol(0).state(PLAY).from_client(0x0e, "ClickWindow", """
    window_id       ubyte
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
    chat_colors     bool
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

#  __     ______     ___  
# /_ |   |____  |   |__ \ 
#  | |       / /       ) |
#  | |      / /       / / 
#  | | _   / /    _  / /_ 
#  |_|(_) /_/    (_)|____|
# 
protocol(4).set_name("1.7.2")
protocol(4).based_on(3)
protocol(4).state(PLAY).from_server(0x22, "MultiBlockChange", """
    chunk_x         int
    chunk_z         int
    changes         changes
""")

#  __     ______       __  
# /_ |   |____  |     / /  
#  | |       / /     / /_  
#  | |      / /     | '_ \ 
#  | | _   / /    _ | (_) |
#  |_|(_) /_/    (_) \___/ 
#
protocol(5).set_name("1.7.6")
protocol(5).based_on(4)
protocol(5).state(PLAY).from_server(0x0c, "SpawnPlayer", """
    eid             varint
    uuid            string
    name            string
    data            varint_player_data_array
    x               int32
    y               int32
    z               int32
    yaw             ubyte
    pitch           ubyte
    current_item    short
    metadata        metadata
""")

#   __      ___  
#  /_ |    / _ \ 
#   | |   | (_) |
#   | |    > _ < 
#   | | _ | (_) |
#   |_|(_) \___/ 
#
protocol(47).set_name("1.8")
protocol(47).based_on(5)
############################################### Login
protocol(47).state(LOGIN).from_server(0x01, "EncryptionRequest", """
    server_id       string
    public_key      varint_byte_array
    challenge_token varint_byte_array
""")
protocol(47).state(LOGIN).from_server(0x03, "SetCompression", """
    threshold       varint
""")
#---------------------------------------------------
protocol(47).state(LOGIN).from_client(0x01, "EncryptionResponse", """
    shared_secret   varint_byte_array
    response_token  varint_byte_array
""")
############################################### Play
protocol(47).state(PLAY).from_server(0x00, "KeepAlive", """
    keepalive_id    varint 
""")
protocol(47).state(PLAY).from_server(0x01, "JoinGame", """
    eid             int
    game_mode       ubyte
    dimension       byte
    difficulty      ubyte
    max_players     ubyte
    level_type      string
    reduced_debug   bool
""")
protocol(47).state(PLAY).from_server(0x02, "ChatMesage", """
    chat            json
    position        byte
""")
protocol(47).state(PLAY).from_server(0x04, "EntityEquipment", """
    eid             varint
    slot            short
    item            slot_1_8
""")
protocol(47).state(PLAY).from_server(0x05, "SpawnPosition", """
    location        position_packed
""")
protocol(47).state(PLAY).from_server(0x06, "HealthUpdate", """
    health          float
    food            varint
    food_saturation float
""")
protocol(47).state(PLAY).from_server(0x08, "PlayerPositionAndLook", """
    x               double
    y               double
    z               double
    yaw             float
    pitch           float
    flag            byte
""")
protocol(47).state(PLAY).from_server(0x0a, "UseBed", """
    eid             varint
    location        position_packed
""")
protocol(47).state(PLAY).from_server(0x0c, "SpawnPlayer", """
    eid             varint
    uuid            uuid
    x               int32
    y               int32
    z               int32
    yaw             ubyte
    pitch           ubyte
    current_item    short
    metadata        metadata_1_8
""")
protocol(47).state(PLAY).from_server(0x0d, "CollectItem", """
    collected_eid   varint
    collector_eid   varint
""")
protocol(47).state(PLAY).from_server(0x10, "SpawnPainting", """
    eid             varint
    title           string
    location        position_packed
    direction       ubyte
""")
protocol(47).state(PLAY).from_server(0x12, "EntityVelocity", """
    eid             varint
    velocity_x      short
    velocity_y      short
    velocity_z      short
""")
protocol(47).state(PLAY).from_server(0x13, "DestroyEntities", """
    eids            varint_varint_array
""")
protocol(47).state(PLAY).from_server(0x14, "Entity", """
    eid             varint
""")
protocol(47).state(PLAY).from_server(0x15, "EntityRelativeMove", """
    eid             varint
    dx              byte32
    dy              byte32
    dz              byte32
    on_ground       bool
""")
protocol(47).state(PLAY).from_server(0x16, "EntityLook", """
    eid             varint
    yaw             ubyte
    pitch           ubyte
    on_ground       bool
""")
protocol(47).state(PLAY).from_server(0x17, "EntityLookAndRelativeMove", """
    eid             varint
    dx              byte32
    dy              byte32
    dz              byte32
    yaw             ubyte
    pitch           ubyte
    on_ground       bool
""")
protocol(47).state(PLAY).from_server(0x18, "EntityTeleport", """
    eid             varint
    x               int32
    y               int32
    z               int32
    yaw             ubyte
    pitch           ubyte
    on_ground       bool
""")
protocol(47).state(PLAY).from_server(0x19, "EntityHeadLook", """
    eid             varint
    head_yaw        ubyte
""")
protocol(47).state(PLAY).from_server(0x1c, "EntityMetadata", """
    eid             varint
    metadata        metadata_1_8
""")
protocol(47).state(PLAY).from_server(0x1d, "EntityEffect", """
    eid             varint
    effect_id       byte
    amplifier       byte
    duration        varint
    hide_particles  bool
""")
protocol(47).state(PLAY).from_server(0x1e, "RemoveEntityEffect", """
    eid             varint
    effect_id       byte
""")
protocol(47).state(PLAY).from_server(0x1f, "SetExperience", """
    bar             float
    level           varint
    total_exp       varint
""")
protocol(47).state(PLAY).from_server(0x20, "EntityProperty", """
    eid             varint
    properties      property_array_14w04a
""")
protocol(47).state(PLAY).from_server(0x21, "ChunkData", """
    chunk_x         int
    chunk_z         int
    continuous      bool
    primary_bitmap  ushort
    data            varint_byte_array
""")
protocol(47).state(PLAY).from_server(0x22, "MultiBlockChange", """
    chunk_x         int
    chunk_z         int
    changes         changes_14w26c
""")
protocol(47).state(PLAY).from_server(0x23, "BlockChange", """
    location        position_packed
    block_id        varint
""")
protocol(47).state(PLAY).from_server(0x24, "BlockAction", """
    location        position_packed
    b1              ubyte
    b2              ubyte
    block_type      varint
""")
protocol(47).state(PLAY).from_server(0x25, "BlockBreakAnimation", """
    eid             varint
    location        position_packed
    destroy_stage   byte
""")
protocol(47).state(PLAY).from_server(0x26, "MapChunkBulk", """
    bulk            map_chunk_bulk_14w28a
""")
protocol(47).state(PLAY).from_server(0x28, "Effect", """
    effect_id       int
    location        position_packed
    data            int
    constant_volume bool
""")
protocol(47).state(PLAY).from_server(0x2a, "Particle", """
    particle_id     int
    long_distance   bool
    x               float
    y               float
    z               float
    offset_x        float
    offset_y        float
    offset_z        float
    speed           float
    number          int
    data            bytes_exhaustive    self.particle_id in (36, 37, 38)
""")
protocol(47).state(PLAY).from_server(0x2d, "OpenWindow", """
    window_id       ubyte
    type            string
    title           json
    slot_count      ubyte
    eid             int                 self.type == "EntityHorse"
""")
protocol(47).state(PLAY).from_server(0x2f, "SetSlot", """
    window_id       ubyte
    slot            short
    item            slot_1_8
""")
protocol(47).state(PLAY).from_server(0x30, "WindowItem", """
    window_id       ubyte
    slots           slot_array_1_8
""")
protocol(47).state(PLAY).from_server(0x33, "UpdateSign", """
    location        position_packed
    line1           json
    line2           json
    line3           json
    line4           json
""")
protocol(47).state(PLAY).from_server(0x34, "Maps", """
    map_id          varint
    scale           byte
    icons           map_icons
    columns         ubyte
    rows            ubyte               self.columns > 0
    x               ubyte               self.columns > 0
    y               ubyte               self.columns > 0
    data            varint_byte_array   self.columns > 0
""")
protocol(47).state(PLAY).from_server(0x35, "UpdateBlockEntity", """
    location        position_packed
    action          ubyte
    nbt             nbt
""")
protocol(47).state(PLAY).from_server(0x36, "SignEditorOpen", """
    location        position_packed
""")
protocol(47).state(PLAY).from_server(0x38, "PlayerListItem", """
    list_actions    list_actions 
""")
protocol(47).state(PLAY).from_server(0x3b, "ScoreboardObjective", """
    name            string
    mode            byte
    value           string              self.mode == 0 or self.mode == 2
    type            string              self.mode == 0 or self.mode == 2
""")
protocol(47).state(PLAY).from_server(0x3c, "UpdateScore", """
    name            string
    remove          byte
    score_name      string
    value           varint              self.remove != 1
""")
protocol(47).state(PLAY).from_server(0x3e, "Teams", """
    team_name           string
    mode                byte
    display_name        string              self.mode in (0, 2)
    prefix              string              self.mode in (0, 2)
    suffix              string              self.mode in (0, 2)
    friendly_fire       byte                self.mode in (0, 2)
    named_tag_visible   string              self.mode in (0, 2)
    color               byte                self.mode in (0, 2) 
    players             varint_string_array self.mode in (0, 3, 4)
""")
protocol(47).state(PLAY).from_server(0x3f, "PluginMessage", """
    channel         string
    data            bytes_exhaustive
""")
protocol(47).state(PLAY).from_server(0x41, "ServerDifficulty", """
    difficulty      ubyte
""")
protocol(47).state(PLAY).from_server(0x42, "CombatEvent", """
    event           ubyte
    duration        varint              self.event == 1
    end_eid         int                 self.event == 1
    player_id       varint              self.event == 2
    dead_eid        int                 self.event == 2
    message         string              self.event == 2
""")
protocol(47).state(PLAY).from_server(0x43, "Camera", """
    camera_id       varint
""")
protocol(47).state(PLAY).from_server(0x44, "WorldBorder", """
    action          varint
    x               double              self.action in (2, 3)
    z               double              self.action in (2, 3)
    old_radius      double              self.action in (1, 3)
    new_radius      double              self.action in (0, 1, 3)
    speed           varint              self.action in (1, 3)
    boundary        varint              self.action == 3
    warning_time    varint              self.action in (3, 4)
    warning_blocks  varint              self.action in (3, 5)
""")
protocol(47).state(PLAY).from_server(0x45, "Title", """
    action          varint
    text            json                self.action in (0, 1)
    fade_in         int                 self.action == 2
    stay            int                 self.action == 2
    fade_out        int                 self.action == 2
""")
protocol(47).state(PLAY).from_server(0x46, "SetCompression", """
    threshold       varint
""")
protocol(47).state(PLAY).from_server(0x47, "PlayerListHeaderFooter", """
    header          json
    footer          json
""")
protocol(47).state(PLAY).from_server(0x48, "ResourcePackSend", """
    url             string
    hash            string
""")
protocol(47).state(PLAY).from_server(0x49, "UpdateEntityNBT", """
    eid             varint
    nbt             short_byte_array
""")
#---------------------------------------------------
protocol(47).state(PLAY).from_client(0x00, "KeepAlive", """
    keepalive_id    varint 
""")
protocol(47).state(PLAY).from_client(0x02, "UseEntity", """
    target          varint
    type            varint
    target_x        float               self.type == 2
    target_y        float               self.type == 2
    target_z        float               self.type == 2
""")
protocol(47).state(PLAY).from_client(0x04, "PlayerPosition", """
    x               double
    y               double
    z               double
    on_ground       bool
""")
protocol(47).state(PLAY).from_client(0x06, "PlayerPositionAndLook", """
    x               double
    y               double
    z               double
    yaw             float
    pitch           float
    on_ground       bool
""")
protocol(47).state(PLAY).from_client(0x07, "PlayerDigging", """
    status          byte
    location        position_packed
    face            byte
""")
protocol(47).state(PLAY).from_client(0x08, "BlockPlacement", """
    location        position_packed
    direction       byte
    held_item       slot_1_8
    cursor_x        byte
    cursor_y        byte
    cursor_z        byte
""")
protocol(47).state(PLAY).from_client(0x0a, "Animation")
protocol(47).state(PLAY).from_client(0x0b, "EntityAction", """
    eid             varint
    action_id       ubyte
    jump_boost      varint
""")
protocol(47).state(PLAY).from_client(0x0c, "SteerVehicle", """
    sideways        float
    forward         float
    flags           ubyte
""")
protocol(47).state(PLAY).from_client(0x0e, "ClickWindow", """
    window_id       ubyte
    slot            short
    button          byte
    action_num      short
    mode            byte
    clicked_item    slot_1_8
""")
protocol(47).state(PLAY).from_client(0x10, "CreativeInventoryAction", """
    slot            short
    clicked_item    slot_1_8
""")
protocol(47).state(PLAY).from_client(0x12, "UpdateSign", """
    location        position_packed
    line1           json
    line2           json
    line3           json
    line4           json
""")
protocol(47).state(PLAY).from_client(0x14, "TabComplete", """
    text            string
    has_position    bool
    location        position_packed     self.has_position
""")
protocol(47).state(PLAY).from_client(0x15, "ClientSettings", """
    locale          string
    view_distance   byte
    chat_flags      byte
    chat_colors     bool
    displayed_skin  ubyte
""")
protocol(47).state(PLAY).from_client(0x16, "ClientStatus", """
    action_id       ubyte
""")
protocol(47).state(PLAY).from_client(0x17, "PluginMessage", """
    channel         string
    data            varint_byte_array
""")
protocol(47).state(PLAY).from_client(0x18, "Spectate", """
    target_player   string
""")
protocol(47).state(PLAY).from_client(0x19, "ResourcePackStatus", """
    hash            string
    result          varint
""")
