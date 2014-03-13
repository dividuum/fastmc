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

import logging
import hashlib
from simplejson import dumps as json_dumps

from Crypto.PublicKey import RSA
from Crypto import Random
from Crypto.Cipher import AES

import requests

log = logging.getLogger(__name__)

def _pkcs1_unpad(bytes):
    pos = bytes.find('\x00')
    if pos > 0:
        return bytes[pos+1:]

def _pkcs1_pad(bytes):
    assert len(bytes) < 117
    padding = ""
    while len(padding) < 125-len(bytes):
        byte = Random.get_random_bytes(1)
        if byte != '\x00':
            padding += byte
    return '\x00\x02%s\x00%s' % (padding, bytes)

def generate_key_pair():
    """Generates a 1024 bit RSA key pair"""
    return RSA.generate(1024)

def encode_public_key(key):
    """Encodes a public RSA key in ASN.1 format as defined by x.509"""
    return key.publickey().exportKey(format="DER")

def generate_random_bytes(length):
    return Random.get_random_bytes(length)

def generate_challenge_token():
    """Generates 4 random bytes"""
    return generate_random_bytes(4)

def generate_server_id():
    """Generates 20 random hex characters"""
    return "".join("%02x" % ord(c) for c in generate_random_bytes(10))

def decrypt_with_private_key(data, private_key):
    """Decrypts the PKCS#1 padded shared secret using the private RSA key"""
    return _pkcs1_unpad(private_key.decrypt(data))

def generated_cipher(shared_secret):
    """Creates a AES128 stream cipher using cfb8 mode"""
    return AES.new(shared_secret, AES.MODE_CFB, shared_secret)

def decode_public_key(bytes):
    """Decodes a public RSA key in ASN.1 format as defined by x.509"""
    return RSA.importKey(bytes)

def generate_shared_secret():
    """Generates a 128 bit secret key to be used in symmetric encryption"""
    return generate_random_bytes(16)

def encrypt_with_public_key(data, public_key):
    """Encrypts the PKCS#1 padded shared secret using the public RSA key"""
    return public_key.encrypt(_pkcs1_pad(data), 0)[0]

class SessionException(Exception):
    pass

class Session(object):
    YGGDRASIL_BASE = "https://authserver.mojang.com"

    @classmethod
    def make_client_token(cls):
        return "".join("%02x" % ord(c) for c in generate_random_bytes(16))

    @classmethod
    def from_credentials(cls, username, password, client_token=None):
        if client_token is None:
            client_token = cls.make_client_token()

        info = cls.do_request("/authenticate", {
            'agent': {
                'name': 'Minecraft',
                'version': 1,
            },
            'username': username,
            'password': password,
            'clientToken': client_token,
        })

        return cls(
            info['accessToken'], 
            info['selectedProfile']['name'], 
            info['selectedProfile']['id']
        )

    @classmethod
    def from_access_token(cls, access_token):
        info = cls.do_request("/refresh", {
            'accessToken': access_token
        })

        return cls(
            info['accessToken'], 
            info['selectedProfile']['name'], 
            info['selectedProfile']['id']
        )

    @classmethod
    def from_authinfo(cls, access_token, player_ign, player_uuid):
        return cls(
            access_token,
            player_ign,
            player_uuid,
        )

    def __init__(self, access_token, player_ign, uuid):
        self._access_token = access_token
        self._player_ign = player_ign
        self._uuid = uuid

    def refresh(self):
        return Session(self._access_token)

    @property
    def player_ign(self):
        return self._player_ign

    @property
    def uuid(self):
        return self._uuid

    @property
    def access_token(self):
        return self._access_token

    @property
    def session_id(self):
        return 'token:%s:%s' % (self._access_token, self._uuid)

    def __str__(self):
        return "<Session: %s (%s) (accessToken: %s)>" % (
            self._player_ign, self._uuid, self._access_token)

    def validate(self):
        r = requests.post(self.YGGDRASIL_BASE + "/validate", data=json_dumps({
            'accessToken': self._access_token
        }))
        return r.status_code == 200

    def invalidate(self):
        r = requests.post(self.YGGDRASIL_BASE + "/invalidate", data=json_dumps({
            'accessToken': self._access_token
        }))
        return r.status_code == 200

    @classmethod
    def do_request(cls, endpoint, data):
        try:
            log.debug("sending %s" % (data,))
            r = requests.post(cls.YGGDRASIL_BASE + endpoint, data=json_dumps(data))
            if not r.ok:
                try:
                    error = r.json()['errorMessage']
                except:
                    error = "unknown error"
                raise SessionException("%d: %s" % (r.status_code, error))
            json = r.json()
            log.debug("received %s" % (json,))
            return json
        except requests.exceptions.RequestException, err:
            raise SessionException(err.message)

def make_server_hash(server_id, shared_secret, key):
    digest = hashlib.sha1()
    digest.update(server_id)
    digest.update(shared_secret)
    digest.update(encode_public_key(key))
    d = long(digest.hexdigest(), 16)
    if d >> 39 * 4 & 0x8:
        return "-%x" % ((-d) & (2 ** (40 * 4) - 1))
    return "%x" % d

def join_server(session, server_hash):
    r = requests.post('https://sessionserver.mojang.com/session/minecraft/join', data=json_dumps({
        'accessToken': session.access_token,
        'selectedProfile': session.uuid,
        'serverId': server_hash,
    }), headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': None,
    })
    return r.status_code == 200

def check_player(player_ign, server_hash):
    r = requests.get('https://sessionserver.mojang.com/session/minecraft/hasJoined?username=%s&serverId=%s' % (
        player_ign, server_hash))
    return None if r.status_code != 200 else r.json()
