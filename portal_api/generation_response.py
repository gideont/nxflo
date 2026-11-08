"""Conservative structured-response decoding without altering substantive values."""
import json
import re


def decode_object(raw,repair_empty_key=False):
    raw=raw.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try:value=json.loads(raw)
    except json.JSONDecodeError:
        if not repair_empty_key:raise
        # Some providers emit ,"} after an otherwise complete object value.
        # Remove only this impossible dangling token outside string literals.
        # Never complete truncated values, alter quoted content, or infer fields.
        parts=[];quoted=False;escaped=False;i=0
        while i<len(raw):
            char=raw[i]
            if not quoted and char==',':
                match=re.match(r',\s*"\s*(?=})',raw[i:])
                if match:i+=match.end();continue
            parts.append(char)
            if quoted:
                if escaped:escaped=False
                elif char=='\\':escaped=True
                elif char=='"':quoted=False
            elif char=='"':quoted=True
            i+=1
        value=json.loads(''.join(parts))
    if not isinstance(value,dict):raise ValueError('Expected a structured object')
    return value
