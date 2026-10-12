"""Parse actual Blender/Cycles status; never estimate completion from elapsed time."""
import re


def sample_percent(line):
    explicit=re.search(r'ALICE_PROGRESS (\d+)',line)
    if explicit:return min(99,int(explicit[1]))
    match=re.search(r'(?:Sample|Rendered)\s+(\d+)\s*/\s*(\d+)',line,re.I)
    if not match:match=re.search(r'Rendering\s+(\d+)\s*/\s*(\d+)\s+samples',line,re.I)
    if match and int(match[2]):return min(99,int(match[1])*100//int(match[2]))
    return None
