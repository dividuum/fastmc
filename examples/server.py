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

import gevent
from gevent.server import StreamServer

import fastmc.auth
import fastmc.proto

class Server(object):
    def __init__(self):
        self.token = fastmc.auth.generate_challenge_token()
        self.server_id = fastmc.auth.generate_server_id()
        self.key = fastmc.auth.generate_key_pair()

    def handle_pkt(self, pkt):
        print pkt
        print

        if self.reader.state == fastmc.proto.HANDSHAKE:
            if pkt.id == 0x00:
                self.reader.switch_state(pkt.state)
                self.writer.switch_state(pkt.state)
        elif self.reader.state == fastmc.proto.STATUS:
            if pkt.id == 0x00:
                out_buf = fastmc.proto.WriteBuffer()
                self.writer.write(out_buf, 0x00, response={
                    "version": {
                        "name": self.reader.protocol.name,
                        "protocol": self.reader.protocol.version,
                    },
                    "players": {
                        "max": 1,
                        "online": 0,
                    },  
                    "description": {"text":"Hello world"},
                })
                self.sock.send(out_buf)
            elif pkt.id == 0x01:
                out_buf = fastmc.proto.WriteBuffer()
                self.writer.write(out_buf, 0x01, 
                    time=pkt.time
                )
                self.sock.send(out_buf)
        elif self.reader.state == fastmc.proto.LOGIN:
            if pkt.id == 0x00:
                out_buf = fastmc.proto.WriteBuffer()

                self.player_ign = pkt.name

                self.writer.write(out_buf, 0x01, 
                    server_id = self.server_id,
                    public_key = fastmc.auth.encode_public_key(self.key),
                    challenge_token = self.token,
                )
                self.sock.send(out_buf)
            elif pkt.id == 0x01:
                decrypted_token = fastmc.auth.decrypt_with_private_key(
                    pkt.response_token, self.key
                )

                if decrypted_token != self.token:
                    raise Exception("Token verification failed")

                shared_secret = fastmc.auth.decrypt_with_private_key(
                    pkt.shared_secret, self.key
                )

                self.sock.set_cipher(
                    fastmc.auth.generated_cipher(shared_secret),
                    fastmc.auth.generated_cipher(shared_secret),
                )

                server_hash = fastmc.auth.make_server_hash(
                    server_id = self.server_id,
                    shared_secret = shared_secret,
                    key = self.key,
                )

                check = fastmc.auth.check_player(self.player_ign, server_hash)
                if not check:
                    raise Exception("Cannot verify your username. Sorry.")

                print check

                out_buf = fastmc.proto.WriteBuffer()
                self.writer.write(out_buf, 0x02, 
                    uuid = check['id'],
                    username = self.player_ign,
                )

                self.reader.switch_state(fastmc.proto.PLAY)
                self.writer.switch_state(fastmc.proto.PLAY)

                self.sock.send(out_buf)
                print "%s logged in" % self.player_ign

        elif self.reader.state == fastmc.proto.PLAY:
            # game play pakets
            pass

    def reader(self, sock):
        protocol_version = 4

        self.sock = fastmc.proto.MinecraftSocket(sock)
        self.reader, self.writer = fastmc.proto.Endpoint.server_pair(protocol_version)

        in_buf = fastmc.proto.ReadBuffer()
        while 1:
            data = self.sock.recv()
            if not data:
                break
            in_buf.append(data)
            while 1:
                pkt, pkt_raw = self.reader.read(in_buf)
                if pkt is None:
                    break
                self.handle_pkt(pkt)

        print "client disconnected"
        sock.close()


def handle(sock, addr):
    gevent.spawn(Server().reader, sock)

listener = StreamServer(('127.0.0.1', 25565), handle)
listener.start()
listener.serve_forever()
