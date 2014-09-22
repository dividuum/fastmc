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

import time
import pprint

import gevent.socket

import fastmc.proto

def pinger(sock, host, port):
    protocol_version = 0

    sock = fastmc.proto.MinecraftSocket(sock)
    in_buf = fastmc.proto.ReadBuffer()
    reader, writer = fastmc.proto.Endpoint.client_pair(protocol_version)

    out_buf = fastmc.proto.WriteBuffer()
    writer.write(out_buf, 0x00, 
        version = writer.protocol.version,
        addr = host,
        port = port,
        state = fastmc.proto.STATUS,
    )
    reader.switch_state(fastmc.proto.STATUS)
    writer.switch_state(fastmc.proto.STATUS)
    writer.write(out_buf, 0x00)
    sock.send(out_buf)

    while 1:
        data = sock.recv()
        if not data:
            break
        in_buf.append(data)

        while 1:
            pkt, pkt_raw = reader.read(in_buf)
            if pkt is None:
                break

            if pkt.id == 0x00:
                out_buf = fastmc.proto.WriteBuffer()
                writer.write(out_buf, 0x01, 
                    time = int(time.time() * 1000)
                )
                sock.send(out_buf)

                pprint.pprint(pkt.response)
            elif pkt.id == 0x01:
                now = int(time.time() * 1000)
                print "%d ms ping" % (now - pkt.time)
                return

def do_ping(host, port):
    sock = gevent.socket.create_connection((host, port), timeout=2)
    try:
        pinger(sock, host, port)
    finally:
        sock.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) <= 1:
        print "%s <host> [<port>]" % sys.argv[0]
        sys.exit(0)
    do_ping(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 25565)
