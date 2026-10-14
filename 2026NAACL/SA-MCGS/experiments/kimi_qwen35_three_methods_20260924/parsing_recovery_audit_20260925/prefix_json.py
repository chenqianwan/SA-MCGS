"""Read exact JSON prefixes without closing containers or inventing values.

``audit_json_prefix(text)`` exposes recursively typed nodes. A node's ``value``
exists only when its complete value is usable. Partial objects retain ``fields``;
partial arrays retain ``items`` and indexed ``complete_elements``. Duplicate
object keys retain all occurrences in an unusable node instead of choosing one.
Offsets are character offsets into the original text. Only an optional leading
Markdown JSON fence is recognized; arbitrary prose is never searched for JSON.
"""
from __future__ import annotations
import json
import math


class _Parser:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.issues = []
        self.failure = None

    def whitespace(self):
        while self.pos < len(self.text) and self.text[self.pos] in ' \t\r\n':
            self.pos += 1

    def unfinished(self, node, message, status='truncated'):
        node.update(end=self.pos, complete=False, usable=False, issue=message)
        if self.failure is None:
            self.failure = status
            self.issues.append({'kind': status, 'offset': self.pos, 'message': message})
        return node

    def value(self, depth=0, root=False):
        self.whitespace()
        start = self.pos
        if depth > 256:
            return self.unfinished(self.node('unknown', start), 'Nesting exceeds audit limit', 'invalid')
        if start == len(self.text):
            return self.unfinished(self.node('unknown', start), 'Expected value at end of input')
        char = self.text[start]
        if char == '{':
            return self.object(depth)
        if char == '[':
            return self.array(depth)
        if char == '"':
            return self.string()
        if char in '-0123456789':
            return self.number(root)
        for token, value, kind in [('true', True, 'boolean'), ('false', False, 'boolean'), ('null', None, 'null')]:
            if char == token[0]:
                node = self.node(kind, start)
                for expected in token:
                    if self.pos == len(self.text):
                        return self.unfinished(node, 'Incomplete literal')
                    if self.text[self.pos] != expected:
                        return self.unfinished(node, 'Invalid literal', 'invalid')
                    self.pos += 1
                if self.pos < len(self.text) and self.text[self.pos] not in ' \t\r\n,]}':
                    return self.unfinished(node, 'Invalid literal boundary', 'invalid')
                node.update(end=self.pos, complete=True, usable=True, value=value)
                return node
        return self.unfinished(self.node('unknown', start), 'Invalid value start', 'invalid')

    @staticmethod
    def node(kind, start):
        return {'kind': kind, 'start': start, 'end': start, 'complete': False, 'usable': False}

    def string(self):
        start = self.pos
        node = self.node('string', start)
        self.pos += 1
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == '"':
                self.pos += 1
                node.update(end=self.pos, complete=True, usable=True,
                            value=json.loads(self.text[start:self.pos]))
                return node
            if ord(char) < 32:
                return self.unfinished(node, 'Unescaped control character', 'invalid')
            if char == '\\':
                self.pos += 1
                if self.pos == len(self.text):
                    return self.unfinished(node, 'Incomplete string escape')
                escape = self.text[self.pos]
                if escape == 'u':
                    self.pos += 1
                    for _ in range(4):
                        if self.pos == len(self.text):
                            return self.unfinished(node, 'Incomplete Unicode escape')
                        if self.text[self.pos] not in '0123456789abcdefABCDEF':
                            return self.unfinished(node, 'Invalid Unicode escape', 'invalid')
                        self.pos += 1
                    continue
                if escape not in '"\\/bfnrt':
                    return self.unfinished(node, 'Invalid string escape', 'invalid')
            self.pos += 1
        return self.unfinished(node, 'Unclosed string')

    def number(self, root):
        start = self.pos
        node = self.node('number', start)
        # Only consume a numeric token; container parsing handles all nesting.
        while self.pos < len(self.text) and self.text[self.pos] not in ' \t\r\n,]}':
            self.pos += 1
        raw = self.text[start:self.pos]
        node['raw'] = raw
        if self.pos == len(self.text) and not root:
            # A truncated trailing 1 might have originally been 12 or 1.5.
            return self.unfinished(node, 'Number at truncated boundary lacks delimiter')
        try:
            value = json.loads(raw)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError('Not a number')
        except (ValueError, json.JSONDecodeError):
            return self.unfinished(node, 'Invalid numeric token', 'invalid')
        node.update(end=self.pos, complete=True, usable=True, value=value)
        if isinstance(value, float) and not math.isfinite(value):
            node.pop('value')
            node.update(usable=False, issue='Number exceeds finite float range')
            self.issues.append({'kind': 'unsupported_number', 'offset': start, 'message': node['issue']})
        return node

    def add_field(self, node, key, child):
        fields = node['fields']
        if key not in fields:
            fields[key] = child
            return
        old = fields[key]
        occurrences = old['occurrences'] if old['kind'] == 'duplicate_key' else [old]
        occurrences.append(child)
        fields[key] = {'kind': 'duplicate_key', 'start': occurrences[0]['start'],
                       'end': child['end'], 'complete': all(c['complete'] for c in occurrences),
                       'usable': False, 'issue': 'Duplicate object key', 'occurrences': occurrences}
        if key not in node['duplicate_keys']:
            node['duplicate_keys'].append(key)
        self.issues.append({'kind': 'duplicate_key', 'offset': child['start'], 'key': key})

    def object(self, depth):
        node = self.node('object', self.pos)
        node.update(fields={}, duplicate_keys=[])
        self.pos += 1
        self.whitespace()
        if self.pos < len(self.text) and self.text[self.pos] == '}':
            self.pos += 1
            node.update(end=self.pos, complete=True, usable=True, value={})
            return node
        while True:
            self.whitespace()
            if self.pos == len(self.text):
                return self.unfinished(node, 'Unclosed object; expected key')
            if self.text[self.pos] != '"':
                return self.unfinished(node, 'Expected quoted object key', 'invalid')
            key = self.string()
            if not key['complete']:
                node['pending_key'] = key
                return self.unfinished(node, 'Incomplete object key', self.failure or 'truncated')
            self.whitespace()
            if self.pos == len(self.text) or self.text[self.pos] != ':':
                child = self.node('unknown', self.pos)
                self.add_field(node, key['value'], child)
                return self.unfinished(node, 'Expected colon after key', 'truncated' if self.pos == len(self.text) else 'invalid')
            self.pos += 1
            child = self.value(depth + 1)
            self.add_field(node, key['value'], child)
            if not child['complete']:
                return self.unfinished(node, 'Incomplete object field', self.failure or 'truncated')
            self.whitespace()
            if self.pos == len(self.text):
                return self.unfinished(node, 'Unclosed object after field')
            delimiter = self.text[self.pos]
            self.pos += 1
            if delimiter == '}':
                usable = all(value['usable'] for value in node['fields'].values())
                node.update(end=self.pos, complete=True, usable=usable)
                if usable:
                    node['value'] = {key: value['value'] for key, value in node['fields'].items()}
                return node
            if delimiter != ',':
                return self.unfinished(node, 'Expected object comma or closing brace', 'invalid')

    def array(self, depth):
        node = self.node('array', self.pos)
        node.update(items=[], complete_elements=[])
        self.pos += 1
        self.whitespace()
        if self.pos < len(self.text) and self.text[self.pos] == ']':
            self.pos += 1
            node.update(end=self.pos, complete=True, usable=True, value=[])
            return node
        while True:
            child = self.value(depth + 1)
            index = len(node['items'])
            node['items'].append(child)
            if child['complete'] and child['usable']:
                node['complete_elements'].append({'index': index, 'value': child['value']})
            if not child['complete']:
                return self.unfinished(node, 'Incomplete array element', self.failure or 'truncated')
            self.whitespace()
            if self.pos == len(self.text):
                return self.unfinished(node, 'Unclosed array after element')
            delimiter = self.text[self.pos]
            self.pos += 1
            if delimiter == ']':
                usable = all(item['usable'] for item in node['items'])
                node.update(end=self.pos, complete=True, usable=usable)
                if usable:
                    node['value'] = [item['value'] for item in node['items']]
                return node
            if delimiter != ',':
                return self.unfinished(node, 'Expected array comma or closing bracket', 'invalid')


def audit_json_prefix(text):
    if not isinstance(text, str):
        raise TypeError('Expected response text as str')
    parser = _Parser(text)
    parser.whitespace()
    wrapper = None
    if text.startswith('```', parser.pos):
        end = text.find('\n', parser.pos)
        header = text[parser.pos:end].strip().lower() if end >= 0 else ''
        if header in ('```', '```json'):
            wrapper = 'markdown_json_fence'
            parser.pos = end + 1
    root = parser.value(root=True)
    parser.whitespace()
    if wrapper and text.startswith('```', parser.pos):
        parser.pos += 3
        parser.whitespace()
    if root['complete'] and parser.pos < len(text):
        parser.failure = 'invalid'
        parser.issues.append({'kind': 'trailing_data', 'offset': parser.pos})
    status = parser.failure or ('complete' if root['usable'] else 'invalid')
    fields = root.get('fields', {})
    return {'status': status, 'root': root, 'complete_fields': {
                key: value['value'] for key, value in fields.items() if value['complete'] and value['usable']},
            'unfinished_fields': [key for key, value in fields.items() if not value['complete']],
            'issues': parser.issues, 'wrapper': wrapper, 'consumed_chars': parser.pos,
            'source_chars': len(text), 'offset_unit': 'unicode_characters'}


if __name__ == '__main__':
    import argparse
    import sys
    from pathlib import Path
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('file', nargs='?', type=Path)
    options = command.parse_args()
    source = options.file.read_text() if options.file else sys.stdin.read()
    print(json.dumps(audit_json_prefix(source), indent=2, ensure_ascii=True, allow_nan=False))
