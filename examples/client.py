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

import sys
import logging
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

import gevent.socket

import fastmc.proto
import fastmc.auth

def handle_pkt(session, reader, writer, sock, pkt):
    if reader.state == fastmc.proto.LOGIN:
        if pkt.id == 0x01:
            if pkt.public_key != '':
                rsa_key = fastmc.auth.decode_public_key(pkt.public_key)
                shared_secret = fastmc.auth.generate_shared_secret()

                response_token = fastmc.auth.encrypt_with_public_key(
                    pkt.challenge_token,
                    rsa_key
                )
                encrypted_shared_secret = fastmc.auth.encrypt_with_public_key(
                    shared_secret,
                    rsa_key
                )

                server_hash = fastmc.auth.make_server_hash(
                    pkt.server_id,
                    shared_secret,
                    rsa_key,
                )

                fastmc.auth.join_server(session, server_hash)

                out_buf = fastmc.proto.WriteBuffer()
                writer.write(out_buf, 0x01, 
                    shared_secret = encrypted_shared_secret,
                    response_token = response_token,
                )
                sock.send(out_buf)

                sock.set_cipher(
                    fastmc.auth.generated_cipher(shared_secret),
                    fastmc.auth.generated_cipher(shared_secret),
                )
            else:
                out_buf = fastmc.proto.WriteBuffer()
                writer.write(out_buf, 0x01, 
                    shared_secret = '',
                    response_token = pkt.challenge_token,
                )
                sock.send(out_buf)
        elif pkt.id == 0x02:
            reader.switch_state(fastmc.proto.PLAY)
            writer.switch_state(fastmc.proto.PLAY)
        elif pkt.id == 0x03:
            reader.set_compression_threshold(pkt.threshold)
            # writer.set_compression_threshold(pkt.threshold)
    elif reader.state == fastmc.proto.PLAY:
        if pkt.id == 0x00:
            print "keep alive!"
            # out_buf = fastmc.proto.WriteBuffer()
            # writer.write(out_buf, 0x00, 
            #     keepalive_id = pkt.keepalive_id
            # )
            # sock.send(out_buf)
        elif pkt.id == 0x46:
            reader.set_compression_threshold(pkt.threshold)

    print pkt
    print

def client(session, sock, host, port):
    protocol_version = 47

    sock = fastmc.proto.MinecraftSocket(sock)
    in_buf = fastmc.proto.ReadBuffer()
    reader, writer = fastmc.proto.Endpoint.client_pair(protocol_version)

    out_buf = fastmc.proto.WriteBuffer()
    writer.write(out_buf, 0x00, 
        version = writer.protocol.version,
        addr = host,
        port = port,
        state = fastmc.proto.LOGIN,
    )
    reader.switch_state(fastmc.proto.LOGIN)
    writer.switch_state(fastmc.proto.LOGIN)
    writer.write(out_buf, 0x00, 
        name = session.player_ign,
    )
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
            handle_pkt(session, reader, writer, sock, pkt)
    sock.close()

def do_client(username, password, host, port):
    session = fastmc.auth.Session.from_credentials(username, password)
    sock = gevent.socket.create_connection((host, port), timeout=2)
    try:
        client(session, sock, host, port)
    finally:
        sock.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) <= 3:
        print "%s <username> <password> <host> [<port>]" % sys.argv[0]
        sys.exit(0)
    do_client(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 25565)
