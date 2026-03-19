#!/usr/bin/env python3
"""Extract JSON object from Claude CLI output (handles multi-line, code fences, preamble)."""
import sys, json, re

text = sys.stdin.read()

# Strategy 1: code fence extraction (```json ... ```)
match = re.search(r'`{3}(?:json)?\s*(\{[\s\S]*?\})\s*`{3}', text)
if match:
    try:
        data = json.loads(match.group(1))
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.exit(0)
    except json.JSONDecodeError:
        pass

# Strategy 2: first { to last }
first = text.find('{')
last = text.rfind('}')
if first != -1 and last > first:
    try:
        data = json.loads(text[first:last+1])
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.exit(0)
    except json.JSONDecodeError:
        pass

# Strategy 3: single-line fallback
for line in text.split('\n'):
    line = line.strip()
    if line.startswith('{') and line.endswith('}'):
        try:
            data = json.loads(line)
            json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
            sys.exit(0)
        except json.JSONDecodeError:
            pass

sys.stderr.write(f'extract_json: failed to parse {len(text)} bytes\n')
json.dump({'error': 'failed to parse output', 'raw_length': len(text)}, sys.stdout)
