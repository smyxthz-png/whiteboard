#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate groups.json from SRT file
Groups subtitles by semantic meaning for storyboard generation
"""

import json
import sys
from pathlib import Path


def parse_srt(srt_path):
    """Parse SRT file and return list of subtitle entries"""
    content = Path(srt_path).read_text(encoding='utf-8')
    entries = []

    blocks = content.strip().split('\n\n')
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            index = int(lines[0])
            time_range = lines[1]
            text = ' '.join(lines[2:])
            entries.append({
                'index': index,
                'time': time_range,
                'text': text
            })

    return entries


def group_subtitles(entries, group_size=3):
    """Group subtitles into semantic groups"""
    groups = []

    for i in range(0, len(entries), group_size):
        group_entries = entries[i:i+group_size]
        from_index = group_entries[0]['index']
        to_index = group_entries[-1]['index']

        group = {
            'sceneId': f'scene_{str(len(groups) + 1).zfill(3)}',
            'fromIndex': from_index,
            'toIndex': to_index,
            'semanticTags': ['whiteboard', 'education'],
            'visualHint': ' '.join(e['text'] for e in group_entries)
        }
        groups.append(group)

    return groups


def main():
    if len(sys.argv) < 3:
        print('Usage: python generate_groups.py <srt-path> <output-path>')
        sys.exit(1)

    srt_path = sys.argv[1]
    output_path = sys.argv[2]

    print(f'[GROUPS] Parsing SRT: {srt_path}')
    entries = parse_srt(srt_path)
    print(f'[OK] Found {len(entries)} subtitle entries')

    print('[GROUPS] Grouping subtitles...')
    groups = group_subtitles(entries, group_size=3)
    print(f'[OK] Created {len(groups)} groups')

    # Write groups.json
    output = {
        'groups': groups
    }

    Path(output_path).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Groups saved to: {output_path}')


if __name__ == '__main__':
    main()
