#!/bin/bash
# ABOUTME: Pipes a batch of translations into `gettext-auto apply` and summarises it,
# ABOUTME: filtering out the expected duplicate-msgid refusals so real failures stand out.
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "usage: $0 <lang> <batch.json>" >&2
    exit 1
fi

uv run gettext-auto apply "$1" --input - < "$2" 2>/dev/null | python3 -c "
import json, sys

result = json.load(sys.stdin)
bad = [
    entry
    for entry in result['entries']
    if entry['status'] != 'ok'
    and not entry['errors'][0].startswith('Refusing to overwrite clean')
]
print('SUMMARY', result['summary'], '| non-dup failures:', len(bad))
for entry in bad:
    print('  !', entry['id'][:8], entry['errors'])
"
