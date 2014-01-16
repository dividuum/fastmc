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
from itertools import count

MC_FORMAT_PATTERN = re.compile(ur"§(.)")

MinecraftChatStyle = namedtuple("MinecraftChatStyle", "rgb bold strikethrough underline italic obfuscated url")

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

DEFAULT_STYLE = MinecraftChatStyle(
    rgb = COLOR_NAMES[DEFAULT_COLOR],
    bold = False,
    strikethrough = False,
    underline = False,
    italic = False,
    obfuscated = False,
    url = None
)


def parse_minecraft_legacy(string, style=DEFAULT_STYLE):
    out = []
    start = 0
    for m in MC_FORMAT_PATTERN.finditer(string):
        end = m.start()
        text = string[start:end]
        if text:
            out.append((text, style))
        code = m.group(1)
        if code in COLOR_CODES:
            style = style._replace(
                rgb = COLOR_CODES[code],
                bold = False,
                strikethrough = False,
                underline = False,
                italic = False,
            )
        elif code == 'l':
            style = style._replace(bold = True)
        elif code == 'm':
            style = style._replace(strikethrough = True)
        elif code == 'n':
            style = style._replace(underline = True)
        elif code == 'o':
            style = style._replace(italic = True)
        elif code == 'k':
            style = style._replace(obfuscated = True)
        elif code == 'r':
            style = DEFAULT_STYLE # XXX: Maybe keep url?
        start = m.end()

    rest = string[start:]
    if rest:
        out.append((rest, style))
    return out


TRANSLATION_PATTERN = re.compile("%(?:([0-9]+)\$)?([ds%])")

class Translation(object):
    def __init__(self, stream):
        self._translations = {}
        for line in stream:
            line = line.strip()
            if not line:
                continue
            key, value = line.split('=', 1)
            next_pos = count(1).next
            chunks = []
            start = 0
            for m in TRANSLATION_PATTERN.finditer(value):
                end = m.start()
                if end > start:
                    chunks.append(value[start:end])
                pos, fmt = m.groups()
                if pos is None:
                    pos = next_pos()
                else:
                    pos = int(pos)
                if fmt == '%':
                    chunks.append('%')
                else:
                    chunks.append(pos)
                start = m.end()
            rest = value[start:]
            if rest:
                chunks.append(rest)
            self._translations[key] = chunks
    def __getitem__(self, key):
        if not key in self._translations:
            return ['<missing translation: %s>' % key]
        return self._translations[key]

def decode_component(comp, translation):
    def recursive_parse(comp, style):
        out = []
        def get_url(comp):
            ce = comp.get('clickEvent')
            if not ce:
                return None
            if ce.get('action') != 'open_url':
                return None
            return ce.get('value')

        if isinstance(comp, unicode):
            out.extend(parse_minecraft_legacy(comp, style))
        elif isinstance(comp, str):
            out.extend(parse_minecraft_legacy(comp.decode('utf8', 'replace'), style))
        elif isinstance(comp, dict):
            if 'color' in comp:
                style = style._replace(rgb = COLOR_NAMES.get(comp['color'], DEFAULT_RGB))
            if 'bold' in comp:
                style = style._replace(bold = comp['bold'])
            if 'italic' in comp:
                style = style._replace(italic = comp['italic'])
            if 'underline' in comp:
                style = style._replace(underline = comp['underline'])
            if 'strikethrough' in comp:
                style = style._replace(strikethrough = comp['strikethrough'])
            if 'obfuscated' in comp:
                style = style._replace(obfuscated = comp['obfuscated'])
            maybe_url = get_url(comp)
            if maybe_url:
                style = style._replace(url = maybe_url)

            if 'text' in comp:
                out.extend(parse_minecraft_legacy(comp['text'], style))
            elif 'translate' in comp:
                args = [()]
                args.extend(recursive_parse(c, style) for c in comp.get('with', ()))
                if not translation:
                    out.append(recursive_parse("<no translation: %s>" % comp['translate'], style))
                else:
                    chunks = translation[comp['translate']]
                    for chunk in chunks:
                        if isinstance(chunk, int):
                            if 0 < chunk < len(args):
                                out.extend(args[chunk])
                        else:
                            out.extend(recursive_parse(chunk, style))
            for extra in comp.get('extra', ()):
                out.extend(recursive_parse(extra, style._replace(url=None)))
        else:
            # invalid data type for component. ignore?
            pass
        return out

    return recursive_parse(comp, style=DEFAULT_STYLE)

class MCString(object):
    def __init__(self, string, translation=None):
        self._components = decode_component(string, translation)

    def to_html(self, allow_links=False):
        def to_style(style):
            styles = []
            styles.append('color:#%02x%02x%02x;' % style.rgb)
            if style.underline:
                styles.append('text-decoration:underline;')
            if style.strikethrough:
                styles.append('text-decoration:line-through;')
            if style.bold:
                styles.append('font-weight:bold;')
            if style.italic:
                styles.append('font-style:italic;')
            return ''.join(styles)

        def fmt_line(style, line):
            if style.url and allow_links:
                return '<a class="chat-link" href="%s" style="%s">%s</a>' % (escape(style.url, quote=True), to_style(style), line)
            else:
                return "<span style='%s'>%s</span>" % (to_style(style), line)

        return ''.join((
            '<br/>'.join(fmt_line(style, line) for line in text.split('\n'))
        ) for text, style in self._components)

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
    test({'text': 'click me', 'clickEvent': {'action': 'open_url', 'value': 'http://example.net'}})
