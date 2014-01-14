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
from cgi import escape
from collections import namedtuple

MC_FORMAT_PATTERN = re.compile(ur"§(.)")

MinecraftFormat = namedtuple("MinecraftFormat", "rgb bold strikethrough underline italic obfuscated url")

CHAT_COLORS = [
    ('black',        '0', (0  ,0  ,0  )),
    ('dark_blue',    '1', (0  ,0  ,170)),
    ('dark_green',   '2', (0  ,170,0  )),
    ('dark_aqua',    '3', (0  ,170,170)),
    ('dark_red',     '4', (170,0  ,0  )),
    ('dark_purple',  '5', (170,0  ,170)),
    ('gold',         '6', (255,170,0  )),
    ('gray',         '7', (170,170,170)),
    ('dark_gray',    '8', (85 ,85 ,85 )),
    ('blue',         '9', (85 ,85 ,255)),
    ('green',        'a', (85 ,255,85 )),
    ('aqua',         'b', (85 ,255,255)),
    ('red',          'c', (255,85 ,85 )),
    ('light_purple', 'd', (255,85 ,255)),
    ('yellow',       'e', (255,255,85 )),
    ('white',        'f', (255,255,255)),
]

COLOR_CODES = dict((code, rgb) for _, code, rgb in CHAT_COLORS)
COLOR_NAMES = dict((name, rgb) for name, _, rgb in CHAT_COLORS)

DEFAULT_COLOR = 'white'
DEFAULT_RGB = COLOR_NAMES[DEFAULT_COLOR]

def parse_minecraft_legacy(string, rgb=DEFAULT_RGB, bold=False, 
        strikethrough=False, underline=False, italic=False, obfuscated=False, url=None):

    components = []
    start = 0

    text_format = MinecraftFormat(rgb, bold, strikethrough, underline, italic, obfuscated, url) 
    for fmt in MC_FORMAT_PATTERN.finditer(string):
        end = fmt.start()
        text = string[start:end]
        code = fmt.group(1)
        if code in COLOR_CODES:
            rgb = COLOR_CODES[code]
            bold = False
            strikethrough = False
            underline = False
            italic = False
        elif code == 'l':
            bold = True
        elif code == 'm':
            strikethrough = True
        elif code == 'n':
            underline = True
        elif code == 'o':
            italic = True
        elif code == 'k':
            obfuscated = True
        elif code == 'r':
            rgb = DEFAULT_RGB
            bold = False
            strikethrough = False
            underline = False
            italic = False
            obfuscated = False

        if text:
            components.append((text, text_format))
        text_format = MinecraftFormat(rgb, bold, strikethrough, underline, italic, obfuscated, url) 
        start = fmt.end()

    rest = string[start:]
    if rest:
        components.append((rest, text_format))

    return components

def decode_component(comp):
    components = []
    def recursive_parse(comp):
        def get_url(comp):
            ce = comp.get('clickEvent')
            if not ce:
                return None
            if ce.get('action') != 'open_url':
                return None
            return ce.get('value')

        if isinstance(comp, unicode):
            components.extend(parse_minecraft_legacy(comp))
        elif isinstance(comp, str):
            components.extend(parse_minecraft_legacy(comp.decode('utf8', 'replace')))
        elif isinstance(comp, dict):
            components.extend(parse_minecraft_legacy(
                string = comp['text'],
                rgb = COLOR_NAMES.get(comp.get('color', DEFAULT_COLOR), DEFAULT_RGB),
                bold = comp.get('bold', False),
                italic = comp.get('italic', False),
                underline = comp.get('underline', False),
                strikethrough = comp.get('strikethrough', False),
                obfuscated = comp.get('obfuscated', False),
                url = get_url(comp),
            ))
            for extra in comp.get('extra', ()):
                recursive_parse(extra)
        else:
            # invalid data type for component. ignore?
            pass
    recursive_parse(comp)
    return components

class MCString(object):
    def __init__(self, string):
        self._components = decode_component(string)

    def to_html(self, allow_links=False):
        def to_style(fmt):
            styles = []
            styles.append('color:#%02x%02x%02x;' % fmt.rgb)
            if fmt.underline:
                styles.append('text-decoration:underline;')
            if fmt.strikethrough:
                styles.append('text-decoration:line-through;')
            if fmt.bold:
                styles.append('font-weight:bold;')
            if fmt.italic:
                styles.append('font-style:italic;')
            return ''.join(styles)

        def fmt_line(fmt, line):
            if fmt.url and allow_links:
                return '<a class="chat-link" href="%s" style="%s">%s</a>' % (escape(fmt.url, quote=True), to_style(fmt), line)
            else:
                return "<span style='%s'>%s</span>" % (to_style(fmt), line)

        return ''.join((
            '<br/>'.join(fmt_line(fmt, line) for line in text.split('\n'))
        ) for text, fmt in self._components)

    @property
    def stripped(self):
        return ''.join(text for text, color in self._components)

def strip_text(string):
    return MCString(string).stripped

def text_to_html(string, allow_links=False):
    return MCString(string).to_html(allow_links)

if __name__ == "__main__":
    def test(string):
        s = MCString(string)
        print repr(s.stripped)
        print s._components
        print repr(s.to_html(False))
        print repr(s.to_html(True))
        print

    test(u"lol")
    test(u"1\n2")
    test(u"lo§4l")
    test({'text': u'lo\xffl', 'extra':[{'text': u'xx§rx', 'color': 'red', 'strikethrough': True}]})
    test({'text': 'click me', 'clickEvent': {'action': 'open_url', 'value': 'http://example.net'}})
