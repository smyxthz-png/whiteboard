#!/usr/bin/env python3
"""
generate-storyboard.py

 SRT  AI  storyboard.json

: python3 generate-storyboard.py <srtPath> <groupsPath> <outputPath>

:
  - srtPath: SRT 
  - groupsPath: AI  groups.json 
  - outputPath:  storyboard.json 

groups.json :
  {
    "groups": [
      {
        "sceneId": "scene_001",
        "fromIndex": 1,
        "toIndex": 3,
        "semanticTags": ["", ""],
        "visualHint": ""
      },
      ...
    ]
  }
"""

import json
import re
import sys


# ============ SRT  ============

def parse_time_code(time_str):
    """"""
    match = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', time_str.strip())
    if not match:
        raise ValueError(f': {time_str}')
    hours, minutes, seconds, ms = match.groups()
    return (
        int(hours) * 3600000 +
        int(minutes) * 60000 +
        int(seconds) * 1000 +
        int(ms)
    )


def parse_srt(srt_content):
    """ SRT """
    subtitles = []

    #  CRLF (\r\n)  LF (\n)
    normalized = srt_content.replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n\s*\n', normalized.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue

        # : 
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue

        # : 
        time_line = lines[1].strip()
        time_match = re.match(r'(.+?)\s*-->\s*(.+)', time_line)
        if not time_match:
            continue

        start_ms = parse_time_code(time_match.group(1))
        end_ms = parse_time_code(time_match.group(2))

        # : 
        text = '\n'.join(lines[2:]).strip()

        subtitles.append({'index': index, 'startMs': start_ms, 'endMs': end_ms, 'text': text})

    # 
    subtitles.sort(key=lambda a: a['index'])

    return subtitles


# ============  ============

def validate_groups(groups, total_subtitles):
    """"""
    errors = []

    if not groups:
        errors.append('')
        return {'valid': False, 'errors': errors}

    #  fromIndex  1
    if groups[0]['fromIndex'] != 1:
        errors.append(f" fromIndex  1 {groups[0]['fromIndex']}")

    #  toIndex 
    last_group = groups[-1]
    if last_group['toIndex'] != total_subtitles:
        errors.append(f" toIndex  {total_subtitles} {last_group['toIndex']}")

    #  sceneId 
    for i, group in enumerate(groups):
        expected_scene_id = f"scene_{str(i + 1).zfill(3)}"

        #  sceneId 
        if group['sceneId'] != expected_scene_id:
            errors.append(f" {i + 1}  sceneId  {expected_scene_id} {group['sceneId']}")

        #  fromIndex <= toIndex
        if group['fromIndex'] > group['toIndex']:
            errors.append(f" {group['sceneId']}  fromIndex ({group['fromIndex']})  toIndex ({group['toIndex']})")

        # 
        if i > 0:
            prev_group = groups[i - 1]
            if group['fromIndex'] != prev_group['toIndex'] + 1:
                errors.append(f" {group['sceneId']}  fromIndex ({group['fromIndex']})  toIndex ({prev_group['toIndex']}) ")

    return {
        'valid': len(errors) == 0,
        'errors': errors
    }


# ============  Storyboard ============

def generate_scenes(subtitles, groups):
    """"""
    scenes = []

    #  (index -> subtitle)
    subtitle_map = {sub['index']: sub for sub in subtitles}

    #  startTime
    group_infos = []
    for group in groups:
        group_subtitles = []
        for idx in range(group['fromIndex'], group['toIndex'] + 1):
            sub = subtitle_map.get(idx)
            if sub:
                group_subtitles.append(sub)
        group_infos.append({'group': group, 'groupSubtitles': group_subtitles})

    #  duration  segments
    for i, info in enumerate(group_infos):
        group = info['group']
        group_subtitles = info['groupSubtitles']

        if not group_subtitles:
            print(f":  {group['sceneId']} ")
            continue

        #  startTime ()
        start_time = group_subtitles[0]['startMs']

        #  segments
        segments = []
        for idx, sub in enumerate(group_subtitles):
            # relativeStart: 
            #  segment  relativeStart  0
            relative_start = 0 if idx == 0 else sub['startMs'] - start_time

            # relativeDuration: 
            relative_duration = sub['endMs'] - sub['startMs']

            segments.append({
                'text': sub['text'],
                'relativeStart': relative_start,
                'relativeDuration': relative_duration
            })

        #  duration
        #  startTime  startTime
        #  startTime
        if i < len(group_infos) - 1:
            next_group_start_time = group_infos[i + 1]['groupSubtitles'][0]['startMs']
            duration = next_group_start_time - start_time
        else:
            last_segment = segments[-1]
            duration = last_segment['relativeStart'] + last_segment['relativeDuration']

        scene = {
            'id': group['sceneId'],
            'startTime': start_time,
            'duration': duration,
            'segments': segments
        }

        # 
        if group.get('semanticTags'):
            scene['semanticTags'] = group['semanticTags']
        if group.get('visualHint'):
            scene['visualHint'] = group['visualHint']

        scenes.append(scene)

    return scenes


def generate_storyboard(scenes):
    """ storyboard """
    if not scenes:
        return {
            'totalDuration': 0,
            'sceneCount': 0,
            'scenes': []
        }

    last_scene = scenes[-1]
    total_duration = last_scene['startTime'] + last_scene['duration']

    return {
        'totalDuration': total_duration,
        'sceneCount': len(scenes),
        'scenes': scenes
    }


# ============  ============

def main():
    args = sys.argv[1:]

    if len(args) < 3:
        print(': python3 generate-storyboard.py <srtPath> <groupsPath> <outputPath>')
        print('')
        print(':')
        print('  srtPath     SRT ')
        print('  groupsPath  AI  groups.json ')
        print('  outputPath   storyboard.json ')
        sys.exit(1)

    srt_path, groups_path, output_path = args[0], args[1], args[2]

    try:
        # 1.  SRT
        print(f'[INFO] Reading SRT file: {srt_path}')
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        subtitles = parse_srt(srt_content)
        print(f'    Parsed {len(subtitles)} subtitles')

        # 2.
        print(f'[INFO] Loading groups: {groups_path}')
        with open(groups_path, 'r', encoding='utf-8') as f:
            groups_data = json.load(f)
        groups = groups_data['groups']
        print(f'    Found {len(groups)} groups')

        # 3.
        print('[INFO] Validating groups...')
        validation = validate_groups(groups, len(subtitles))
        if not validation['valid']:
            print('[ERROR] Validation failed:')
            for err in validation['errors']:
                print(f'   - {err}')
            sys.exit(1)
        print('   [OK] Validation passed')

        # 4.
        print('[INFO] Generating scenes...')
        scenes = generate_scenes(subtitles, groups)

        # 5.  storyboard
        storyboard = generate_storyboard(scenes)

        # 6.
        print(f'[INFO] Writing output: {output_path}')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(storyboard, f, ensure_ascii=False, indent=2)

        # 7.
        print('')
        print('[SUCCESS] Storyboard generation complete!')
        print(f'   - Scene count: {storyboard["sceneCount"]}')
        print(f'   - Total duration: {storyboard["totalDuration"] / 1000:.1f}s')
        print(f'   - Output file: {output_path}')

        #  JSON 
        print('')
        print('__RESULT_JSON__')
        print(json.dumps({
            'success': True,
            'storyboardPath': output_path,
            'sceneCount': storyboard['sceneCount'],
            'totalDuration': storyboard['totalDuration']
        }, ensure_ascii=False))

    except FileNotFoundError as e:
        print(f'[ERROR] File not found: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'[ERROR] Unexpected error: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
