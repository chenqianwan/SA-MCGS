# JSON prefix audit utility

Import `audit_json_prefix` from `prefix_json.py` and pass the unchanged response
text. The function uses only the Python standard library and performs no I/O.

- `complete_fields` contains plain values of complete, usable top-level fields.
- `root.fields[name]` retains nested object fields, including inside an unclosed
  object. A complete `risk_subgraph.nodes` therefore remains available even if
  a later field or the enclosing object was truncated.
- Array nodes expose `items` and indexed `complete_elements`. Every item has its
  own `complete` and `usable` flags. An unclosed row has no inferred value.
- Duplicate keys produce an unusable `duplicate_key` node retaining all
  `occurrences`. No occurrence is silently chosen.
- A number ending exactly at the truncation boundary inside a container is not
  considered complete: the missing suffix could have changed its value.
- Offsets refer to characters in the original response. A leading Markdown JSON
  fence is supported; arbitrary prose and nested braces are not searched.

The utility identifies observed JSON values only. It does not validate clause
identities, rank semantics, metric availability, or experimental success.

Verification: `python -B -m unittest -v test_prefix_json.py` passes 11 tests
covering nested/partial objects, escaped strings, duplicate keys, partial arrays,
truncated numeric tokens, wrapper handling, and malformed input.
