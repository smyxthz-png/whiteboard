#!/usr/bin/env python3

import asyncio
import base64
import json
import os
import random
import struct
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from banana_prompt_template import whiteboard_prompt_template

# --- Config ---
API_BASE = 'https://www.runninghub.cn/openapi/v2'
TEXT_TO_IMAGE_PATH = '/rhart-image-n-g31-flash/text-to-image'
QUERY_PATH = '/query'
RESOLUTION = '2k'

MAX_RETRIES = 3
SUBMIT_MAX_RETRIES = 8
POLL_MAX_RETRIES = 5

RETRY_BASE_DELAY_S = 3.0
POLL_INTERVAL_S = 5.0
T8_POLL_INTERVAL_S = 3.0
T8_MAX_WAIT_S = 360
KIE_POLL_INTERVAL_S = 3.0
KIE_MAX_WAIT_S = 600
APIMART_POLL_INTERVAL_S = 5.0
APIMART_MAX_WAIT_S = 600

BATCH_CONCURRENCY = 10
ASPECT_RATIO_TOLERANCE = 0.03

SCRIPT_DIR = Path(__file__).resolve().parent


def is_valid_file(path):
    try:
        return Path(path).exists() and Path(path).stat().st_size > 1024
    except OSError:
        return False


def parse_aspect_ratio(value):
    try:
        width, height = (int(part) for part in value.split(':', 1))
    except (AttributeError, TypeError, ValueError):
        raise FatalError(f'Invalid aspect ratio: {value!r}')
    if width <= 0 or height <= 0:
        raise FatalError(f'Invalid aspect ratio: {value!r}')
    return width, height


def read_image_dimensions(path):
    """Read PNG/JPEG/WebP dimensions without adding an image dependency."""
    with open(path, 'rb') as handle:
        header = handle.read(32)

        if header.startswith(b'\x89PNG\r\n\x1a\n') and len(header) >= 24:
            return struct.unpack('>II', header[16:24])

        if header[:2] == b'\xff\xd8':
            handle.seek(2)
            while True:
                marker_start = handle.read(1)
                if not marker_start:
                    break
                if marker_start != b'\xff':
                    continue
                marker = handle.read(1)
                while marker == b'\xff':
                    marker = handle.read(1)
                if not marker or marker in {b'\xd8', b'\xd9'}:
                    continue
                length_bytes = handle.read(2)
                if len(length_bytes) != 2:
                    break
                segment_length = struct.unpack('>H', length_bytes)[0]
                if marker[0] in {
                    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
                }:
                    dimensions = handle.read(5)
                    if len(dimensions) == 5:
                        height, width = struct.unpack('>HH', dimensions[1:5])
                        return width, height
                    break
                handle.seek(max(0, segment_length - 2), 1)

        if header.startswith(b'RIFF') and header[8:12] == b'WEBP':
            chunk = header[12:16]
            if chunk == b'VP8X' and len(header) >= 30:
                width = 1 + int.from_bytes(header[24:27], 'little')
                height = 1 + int.from_bytes(header[27:30], 'little')
                return width, height
            if chunk == b'VP8 ' and len(header) >= 30 and header[23:26] == b'\x9d\x01\x2a':
                width, height = struct.unpack('<HH', header[26:30])
                return width & 0x3FFF, height & 0x3FFF
            if chunk == b'VP8L' and len(header) >= 25:
                bits = int.from_bytes(header[21:25], 'little')
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1

    raise RetryableError(f'Unsupported or corrupt image file: {path}')


def validate_image_aspect_ratio(path, aspect_ratio):
    width, height = read_image_dimensions(path)
    expected_width, expected_height = parse_aspect_ratio(aspect_ratio)
    expected = expected_width / expected_height
    actual = width / height
    relative_error = abs(actual - expected) / expected
    if relative_error > ASPECT_RATIO_TOLERANCE:
        raise RetryableError(
            f'Wrong image aspect ratio: got {width}x{height} ({actual:.4f}), '
            f'expected {aspect_ratio} ({expected:.4f}), '
            f'error {relative_error * 100:.1f}% exceeds '
            f'{ASPECT_RATIO_TOLERANCE * 100:.1f}% tolerance.'
        )
    return width, height


def find_existing_image(output_dir, index, total, aspect_ratio=None):
    suffix = str(index + 1).zfill(len(str(total))) if total > 1 else '1'
    candidates = []
    patterns = [
        f'image2_{suffix}_*.png',
        f'banana2_*_{suffix}.png',
        f'banana2_*_{suffix}.jpg',
        f'banana2_*_{suffix}.jpeg',
    ]
    if total == 1:
        patterns.extend(['image2_1_*.png', 'banana2_*.png', 'banana2_*.jpg', 'banana2_*.jpeg'])

    output_path = Path(output_dir)
    for pattern in patterns:
        candidates.extend(path for path in output_path.glob(pattern) if is_valid_file(path))

    if not candidates:
        return None
    for candidate in sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True):
        if aspect_ratio:
            try:
                validate_image_aspect_ratio(candidate, aspect_ratio)
            except (OSError, RetryableError):
                continue
        return str(candidate)
    return None


# --- Load .env from skill directory ---
def load_env():
    env_path = SCRIPT_DIR.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            trimmed = line.strip()
            if not trimmed or trimmed.startswith('#'):
                continue
            eq_index = trimmed.find('=')
            if eq_index == -1:
                continue
            key = trimmed[:eq_index].strip()
            value = trimmed[eq_index + 1:].strip().strip('"').strip("'")
            if key and value and not os.environ.get(key):
                os.environ[key] = value


def get_image_provider():
    provider = os.environ.get('IMAGE_PROVIDER', 'runninghub').strip().lower()
    if provider in {'t8', 't8_image2', 't8star', 't8star_image2'}:
        return 't8_image2'
    if provider in {'macode', 'macode_image2', 'image2', 'gpt-image-2'}:
        return 'macode_image2'
    if provider in {'kie', 'kie_ai', 'kie_image2', 'kieai', 'kie-gpt-image-2'}:
        return 'kie_image2'
    if provider in {'apimart', 'api_mart', 'apimart_image2', 'apimart-gpt-image-2'}:
        return 'apimart_image2'
    if provider in {'gemini', 'gemini_image', 'google', 'google_gemini'}:
        return 'gemini_image'
    return 'runninghub'


def get_batch_concurrency():
    provider = get_image_provider()
    if provider == 't8_image2':
        env_name = 'T8_IMAGE_CONCURRENCY'
        default_value = 3
    elif provider == 'macode_image2':
        env_name = 'MACODE_IMAGE_CONCURRENCY'
        default_value = 3
    elif provider == 'kie_image2':
        env_name = 'KIE_IMAGE_CONCURRENCY'
        default_value = 3
    elif provider == 'apimart_image2':
        env_name = 'APIMART_IMAGE_CONCURRENCY'
        default_value = 8
    elif provider == 'gemini_image':
        env_name = 'GEMINI_IMAGE_CONCURRENCY'
        default_value = 3
    else:
        env_name = 'IMAGE_BATCH_CONCURRENCY'
        default_value = BATCH_CONCURRENCY
    try:
        return max(1, int(os.environ.get(env_name, default_value)))
    except ValueError:
        return default_value


def normalize_image_size(value, aspect_ratio):
    normalized = (value or '').strip().lower()
    legacy_sizes = {
        '1920x1080': '1792x1008',
        '1080x1920': '1008x1792',
    }
    if normalized in legacy_sizes:
        return legacy_sizes[normalized]
    if normalized in {'16:9', 'landscape', 'horizontal'}:
        return '1792x1008'
    if normalized in {'9:16', 'portrait', 'vertical'}:
        return '1008x1792'
    if normalized in {'1:1', 'square'}:
        return '1024x1024'
    if 'x' in normalized:
        return normalized
    sizes = {
        '16:9': '1792x1008',
        '9:16': '1008x1792',
        '1:1': '1024x1024',
    }
    return sizes.get(aspect_ratio, '1792x1008')


def image_size_for_aspect_ratio(aspect_ratio):
    provider = get_image_provider()
    if provider == 't8_image2' and os.environ.get('T8_IMAGE_SIZE'):
        return normalize_image_size(os.environ['T8_IMAGE_SIZE'], aspect_ratio)
    if provider == 'macode_image2' and os.environ.get('MACODE_IMAGE_SIZE'):
        return normalize_image_size(os.environ['MACODE_IMAGE_SIZE'], aspect_ratio)
    if provider == 'apimart_image2':
        return normalize_image_size(os.environ.get('APIMART_IMAGE_SIZE', '1792x1008'), aspect_ratio)
    return normalize_image_size('', aspect_ratio)


def gemini_image_config(aspect_ratio):
    config = {'aspectRatio': aspect_ratio}
    image_size = os.environ.get('GEMINI_IMAGE_SIZE', '2K').strip().upper()
    if image_size:
        config['imageSize'] = image_size
    return config


def decode_data_uri(data_uri):
    if not data_uri.startswith('data:image') or ',' not in data_uri:
        return None
    return base64.b64decode(data_uri.split(',', 1)[1])


def save_image_result(image_result, filepath):
    b64_json = image_result.get('b64_json')
    if b64_json:
        Path(filepath).write_bytes(base64.b64decode(b64_json))
        return filepath

    image_url = image_result.get('url')
    if image_url and image_url.startswith('data:image'):
        image_bytes = decode_data_uri(image_url)
        if not image_bytes:
            raise RetryableError('Invalid data URI in image response.')
        Path(filepath).write_bytes(image_bytes)
        return filepath
    if image_url:
        parsed = urlparse(image_url)
        if parsed.scheme not in {'http', 'https'}:
            raise RetryableError(f'Unsupported image URL scheme: {parsed.scheme}')
        download_file(image_url, filepath)
        return filepath

    raise RetryableError('Image response did not contain b64_json or url.')


def normalized_openai_base_url(env_name, default):
    base_url = os.environ.get(env_name, default).strip().rstrip('/')
    if not base_url:
        return ''
    if not base_url.endswith('/v1'):
        base_url = f'{base_url}/v1'
    return base_url


def request_openai_json_sync(method, url, api_key, body=None, timeout=180):
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = Request(url, data=payload, method=method)
    req.add_header('Authorization', f'Bearer {api_key}')
    if payload is not None:
        req.add_header('Content-Type', 'application/json; charset=utf-8')

    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode('utf-8')
            return json.loads(data)
    except HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        if e.code in {400, 401, 403}:
            raise FatalError(f'HTTP {e.code}: {body_text}')
        if e.code == 429:
            raise RetryableError(f'HTTP 429 (rate limited): {body_text}', is_rate_limit=True)
        raise RetryableError(f'HTTP {e.code}: {body_text}')
    except json.JSONDecodeError as e:
        raise RetryableError(f'Failed to parse image provider response: {e}')
    except Exception as e:
        raise RetryableError(str(e))


def extract_gemini_image(response):
    """Return the last non-thinking inline image from a Gemini response."""
    images = []
    for candidate in response.get('candidates', []) if isinstance(response, dict) else []:
        content = candidate.get('content', {}) if isinstance(candidate, dict) else {}
        for part in content.get('parts', []) if isinstance(content, dict) else []:
            if not isinstance(part, dict) or part.get('thought'):
                continue
            inline_data = part.get('inlineData') or part.get('inline_data')
            if not isinstance(inline_data, dict):
                continue
            data = inline_data.get('data')
            mime_type = inline_data.get('mimeType') or inline_data.get('mime_type') or ''
            if data and str(mime_type).startswith('image/'):
                images.append(data)
    return images[-1] if images else None


def request_gemini_image_sync(prompt, aspect_ratio):
    api_key = os.environ.get('GEMINI_API_KEY')
    model = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-3.1-flash-image').strip()
    base_url = os.environ.get(
        'GEMINI_BASE_URL',
        'https://generativelanguage.googleapis.com/v1',
    ).strip().rstrip('/')
    if not api_key:
        raise FatalError('GEMINI_API_KEY not found. Set it in .env or environment variables.')
    if not model:
        raise FatalError('GEMINI_IMAGE_MODEL is empty.')
    if not base_url.startswith('https://'):
        raise FatalError('GEMINI_BASE_URL must use HTTPS.')

    body = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'responseModalities': ['IMAGE'],
            'imageConfig': gemini_image_config(aspect_ratio),
        },
    }
    payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = Request(f'{base_url}/models/{model}:generateContent', data=payload, method='POST')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    req.add_header('X-goog-api-key', api_key)
    try:
        with urlopen(req, timeout=180) as resp:
            response = json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        if e.code in {400, 401, 403, 404}:
            raise FatalError(f'Gemini HTTP {e.code}: {body_text}')
        if e.code == 429:
            raise RetryableError(f'Gemini HTTP 429 (rate limited): {body_text}', is_rate_limit=True)
        raise RetryableError(f'Gemini HTTP {e.code}: {body_text}')
    except json.JSONDecodeError as e:
        raise RetryableError(f'Failed to parse Gemini response: {e}')
    except Exception as e:
        raise RetryableError(str(e))

    image_data = extract_gemini_image(response)
    if not image_data:
        raise RetryableError('Gemini response did not contain a generated image.')
    return {'data': [{'b64_json': image_data}]}


def find_openai_image_response(value):
    if isinstance(value, dict):
        data = value.get('data')
        if isinstance(data, list):
            return value
        for key in ('data', 'result', 'response', 'output'):
            found = find_openai_image_response(value.get(key))
            if found:
                return found
    return None


def extract_task_id(value):
    if not isinstance(value, dict):
        return None
    for key in ('task_id', 'taskId', 'id'):
        task_id = value.get(key)
        if isinstance(task_id, str) and task_id.strip():
            return task_id.strip()
    nested = value.get('data')
    if isinstance(nested, dict):
        return extract_task_id(nested)
    if isinstance(nested, list):
        for item in nested:
            task_id = extract_task_id(item)
            if task_id:
                return task_id
    return None


def request_apimart_json_sync(method, path, api_key, body=None, timeout=180):
    base_url = normalized_openai_base_url('APIMART_BASE_URL', 'https://api.apimart.ai').strip().rstrip('/')
    if not base_url:
        raise FatalError('APIMART_BASE_URL not found. Set it in .env or environment variables.')
    path = path if path.startswith('/') else f'/{path}'
    return request_openai_json_sync(method, f'{base_url}{path}', api_key, body=body, timeout=timeout)


def find_apimart_result_urls(value):
    urls = []
    if isinstance(value, dict):
        result = value.get('result')
        if isinstance(result, dict):
            found = find_apimart_result_urls(result)
            if found:
                return found
        images = value.get('images')
        if isinstance(images, list):
            for image in images:
                if isinstance(image, str) and image.startswith(('http://', 'https://', 'data:image')):
                    urls.append(image)
                elif isinstance(image, dict):
                    raw_url = image.get('url') or image.get('image_url') or image.get('imageUrl')
                    if isinstance(raw_url, str) and raw_url.startswith(('http://', 'https://', 'data:image')):
                        urls.append(raw_url)
                    elif isinstance(raw_url, list):
                        urls.extend(
                            item for item in raw_url
                            if isinstance(item, str) and item.startswith(('http://', 'https://', 'data:image'))
                        )
            if urls:
                return urls
        for key in ('data', 'response', 'output'):
            found = find_apimart_result_urls(value.get(key))
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_apimart_result_urls(item)
            if found:
                return found
    return urls


def apimart_status_from_response(value):
    if not isinstance(value, dict):
        return ''
    data = value.get('data') if isinstance(value.get('data'), dict) else value
    for key in ('status', 'state', 'taskStatus', 'task_status'):
        status = data.get(key)
        if status is not None:
            return str(status).strip().lower()
    return ''


def request_apimart_image_sync(prompt, aspect_ratio):
    api_key = os.environ.get('APIMART_API_KEY')
    model = os.environ.get('APIMART_IMAGE_MODEL', 'gpt-image-2').strip()
    resolution = os.environ.get('APIMART_IMAGE_RESOLUTION', '1k').strip() or '1k'
    if not api_key:
        raise FatalError('APIMART_API_KEY not found. Set it in .env or environment variables.')
    if not model:
        raise FatalError('APIMART_IMAGE_MODEL is empty.')

    body = {
        'model': model,
        'prompt': prompt,
        'n': 1,
        'size': image_size_for_aspect_ratio(aspect_ratio),
        'resolution': resolution,
    }
    if os.environ.get('APIMART_OFFICIAL_FALLBACK', '').strip().lower() in {'1', 'true', 'yes'}:
        body['official_fallback'] = True

    result = request_apimart_json_sync('POST', '/images/generations', api_key, body=body, timeout=180)
    image_urls = find_apimart_result_urls(result)
    if image_urls:
        return {'data': [{'url': image_urls[0]}]}

    task_id = extract_task_id(result)
    if not task_id:
        raise RetryableError(f'APIMart response did not contain image data or task_id: {json.dumps(result, ensure_ascii=False)}')

    try:
        max_wait_s = max(60.0, float(os.environ.get('APIMART_IMAGE_TIMEOUT', APIMART_MAX_WAIT_S)))
    except ValueError:
        max_wait_s = APIMART_MAX_WAIT_S
    try:
        poll_interval = max(1.0, float(os.environ.get('APIMART_IMAGE_POLL_INTERVAL', APIMART_POLL_INTERVAL_S)))
    except ValueError:
        poll_interval = APIMART_POLL_INTERVAL_S

    deadline = time.monotonic() + max_wait_s
    last_status = ''
    while time.monotonic() < deadline:
        poll_result = request_apimart_json_sync('GET', f'/tasks/{task_id}', api_key, timeout=60)
        image_urls = find_apimart_result_urls(poll_result)
        if image_urls:
            return {'data': [{'url': image_urls[0]}]}

        status = apimart_status_from_response(poll_result)
        if status:
            last_status = status
        if status in {'failed', 'failure', 'error'}:
            raise RetryableError(f'APIMart task failed: {json.dumps(poll_result, ensure_ascii=False)}')
        time.sleep(poll_interval)

    raise RetryableError(f'APIMart task timed out after {max_wait_s:.0f}s for {task_id} (last status: {last_status or "unknown"}).')


def request_kie_json_sync(method, path, api_key, body=None, timeout=180):
    base_url = os.environ.get('KIE_BASE_URL', 'https://api.kie.ai').strip().rstrip('/')
    if not base_url:
        raise FatalError('KIE_BASE_URL not found. Set it in .env or environment variables.')
    url = f'{base_url}{path}'
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = Request(url, data=payload, method=method)
    req.add_header('Authorization', f'Bearer {api_key}')
    if payload is not None:
        req.add_header('Content-Type', 'application/json; charset=utf-8')

    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode('utf-8')
            return json.loads(data)
    except HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        if e.code in {400, 401, 403, 422}:
            raise FatalError(f'HTTP {e.code}: {body_text}')
        if e.code == 429:
            raise RetryableError(f'HTTP 429 (rate limited): {body_text}', is_rate_limit=True)
        raise RetryableError(f'HTTP {e.code}: {body_text}')
    except json.JSONDecodeError as e:
        raise RetryableError(f'Failed to parse Kie response: {e}')
    except Exception as e:
        raise RetryableError(str(e))


def find_kie_result_urls(value):
    urls = []
    if isinstance(value, dict):
        for key in ('resultUrls', 'result_urls', 'imageUrls', 'image_urls', 'urls', 'images'):
            raw = value.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.startswith(('http://', 'https://', 'data:image')):
                        urls.append(item)
                    elif isinstance(item, dict):
                        url = item.get('url') or item.get('image_url') or item.get('imageUrl')
                        if isinstance(url, str) and url.startswith(('http://', 'https://', 'data:image')):
                            urls.append(url)
                if urls:
                    return urls
        for key in ('response', 'result', 'output', 'data'):
            found = find_kie_result_urls(value.get(key))
            if found:
                return found
        result_json = value.get('resultJson') or value.get('result_json')
        if isinstance(result_json, str) and result_json.strip():
            try:
                return find_kie_result_urls(json.loads(result_json))
            except json.JSONDecodeError:
                return []
    elif isinstance(value, list):
        for item in value:
            found = find_kie_result_urls(item)
            if found:
                return found
    return urls


def kie_status_from_response(value):
    if not isinstance(value, dict):
        return ''
    data = value.get('data') if isinstance(value.get('data'), dict) else value
    for key in ('status', 'state', 'taskStatus', 'task_status'):
        status = data.get(key)
        if status is not None:
            return str(status).upper()
    return ''


def request_kie_image_sync(prompt, aspect_ratio):
    api_key = os.environ.get('KIE_API_KEY')
    model = os.environ.get('KIE_IMAGE_MODEL', 'gpt-image-2-text-to-image').strip()
    if not api_key:
        raise FatalError('KIE_API_KEY not found. Set it in .env or environment variables.')
    if not model:
        raise FatalError('KIE_IMAGE_MODEL is empty.')

    body = {
        'model': model,
        'input': {
            'prompt': prompt,
            'aspect_ratio': aspect_ratio,
        },
    }
    resolution = os.environ.get('KIE_IMAGE_RESOLUTION', '').strip()
    if resolution:
        body['input']['resolution'] = resolution

    result = request_kie_json_sync('POST', '/api/v1/jobs/createTask', api_key, body=body, timeout=180)
    code = result.get('code') if isinstance(result, dict) else None
    if code not in (None, 200, '200'):
        raise RetryableError(f'Kie task submission failed: {json.dumps(result, ensure_ascii=False)}')
    task_id = extract_task_id(result)
    if not task_id:
        raise RetryableError(f'Kie response did not contain taskId: {json.dumps(result, ensure_ascii=False)}')

    try:
        max_wait_s = max(60.0, float(os.environ.get('KIE_IMAGE_TIMEOUT', KIE_MAX_WAIT_S)))
    except ValueError:
        max_wait_s = KIE_MAX_WAIT_S
    try:
        poll_interval = max(1.0, float(os.environ.get('KIE_IMAGE_POLL_INTERVAL', KIE_POLL_INTERVAL_S)))
    except ValueError:
        poll_interval = KIE_POLL_INTERVAL_S

    deadline = time.monotonic() + max_wait_s
    last_status = ''
    while time.monotonic() < deadline:
        poll_result = request_kie_json_sync(
            'GET',
            f'/api/v1/jobs/recordInfo?taskId={task_id}',
            api_key,
            timeout=60,
        )
        urls = find_kie_result_urls(poll_result)
        if urls:
            return {'data': [{'url': urls[0]}]}

        status = kie_status_from_response(poll_result)
        if status:
            last_status = status
        if status in {'FAIL', 'FAILED', 'FAILURE', 'ERROR'}:
            raise RetryableError(f'Kie task failed: {json.dumps(poll_result, ensure_ascii=False)}')
        time.sleep(poll_interval)

    raise RetryableError(f'Kie task timed out after {max_wait_s:.0f}s for {task_id} (last status: {last_status or "unknown"}).')


def request_macode_image_sync(prompt, aspect_ratio):
    api_key = os.environ.get('MACODE_API_KEY')
    base_url = os.environ.get('MACODE_BASE_URL', '').rstrip('/')
    model = os.environ.get('MACODE_IMAGE_MODEL', 'gpt-image-2')
    quality = (
        os.environ.get('MACODE_IMAGE_QUALITY')
        or os.environ.get('T8_IMAGE_QUALITY')
        or ''
    ).strip()

    if not api_key:
        raise FatalError('MACODE_API_KEY not found. Set it in .env or environment variables.')
    if not base_url:
        raise FatalError('MACODE_BASE_URL not found. Set it in .env or environment variables.')

    body = {
        'model': model,
        'prompt': prompt,
        'size': image_size_for_aspect_ratio(aspect_ratio),
        'n': 1,
    }
    if quality:
        body['quality'] = quality

    payload = json.dumps(body).encode('utf-8')
    req = Request(f'{base_url}/images/generations', data=payload, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {api_key}')

    try:
        with urlopen(req, timeout=180) as resp:
            data = resp.read().decode('utf-8')
            return json.loads(data)
    except HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        if e.code in {400, 401, 403}:
            raise FatalError(f'HTTP {e.code}: {body_text}')
        if e.code == 429:
            raise RetryableError(f'HTTP 429 (rate limited): {body_text}', is_rate_limit=True)
        raise RetryableError(f'HTTP {e.code}: {body_text}')
    except json.JSONDecodeError as e:
        raise RetryableError(f'Failed to parse macode response: {e}')
    except Exception as e:
        raise RetryableError(str(e))


def request_t8_image_sync(prompt, aspect_ratio):
    api_key = os.environ.get('T8_API_KEY') or os.environ.get('T8STAR_API_KEY')
    base_url = normalized_openai_base_url('T8_BASE_URL', 'https://ai.t8star.cn')
    model = os.environ.get('T8_IMAGE_MODEL', 'gpt-image-2')
    quality = os.environ.get('T8_IMAGE_QUALITY', 'high').strip()
    response_format = os.environ.get('T8_IMAGE_RESPONSE_FORMAT', 'url').strip() or 'url'
    async_mode = os.environ.get('T8_IMAGE_ASYNC', 'true').strip().lower() not in {'0', 'false', 'no'}

    if not api_key:
        raise FatalError('T8_API_KEY not found. Set it in .env or environment variables.')
    if not base_url:
        raise FatalError('T8_BASE_URL not found. Set it in .env or environment variables.')

    body = {
        'model': model,
        'prompt': prompt,
        'size': image_size_for_aspect_ratio(aspect_ratio),
        'n': 1,
        'response_format': response_format,
    }
    if quality:
        body['quality'] = quality

    submit_url = f'{base_url}/images/generations'
    if async_mode:
        submit_url = f'{submit_url}?async=true'

    result = request_openai_json_sync('POST', submit_url, api_key, body=body, timeout=180)
    image_response = find_openai_image_response(result)
    if image_response:
        return image_response

    task_id = extract_task_id(result)
    if not task_id:
        raise RetryableError(f'T8 response did not contain image data or task_id: {json.dumps(result, ensure_ascii=False)}')

    try:
        max_wait_s = max(60.0, float(os.environ.get('T8_IMAGE_TIMEOUT', T8_MAX_WAIT_S)))
    except ValueError:
        max_wait_s = T8_MAX_WAIT_S
    try:
        poll_interval = max(1.0, float(os.environ.get('T8_IMAGE_POLL_INTERVAL', T8_POLL_INTERVAL_S)))
    except ValueError:
        poll_interval = T8_POLL_INTERVAL_S

    deadline = time.monotonic() + max_wait_s
    poll_url = f'{base_url}/images/tasks/{task_id}'
    last_status = ''

    while time.monotonic() < deadline:
        poll_result = request_openai_json_sync('GET', poll_url, api_key, timeout=60)
        image_response = find_openai_image_response(poll_result)
        status_payload = poll_result.get('data') if isinstance(poll_result, dict) and isinstance(poll_result.get('data'), dict) else poll_result
        status = str(status_payload.get('status', '') if isinstance(status_payload, dict) else '').upper()
        if status:
            last_status = status

        if status in {'SUCCESS', 'SUCCEEDED', 'COMPLETED', 'DONE'} and image_response:
            return image_response
        if status in {'FAILURE', 'FAILED', 'ERROR'}:
            reason = ''
            if isinstance(status_payload, dict):
                reason = status_payload.get('fail_reason') or status_payload.get('error') or status_payload.get('message') or ''
            raise RetryableError(f'T8 task failed: {reason or json.dumps(poll_result, ensure_ascii=False)}')

        time.sleep(poll_interval)

    raise RetryableError(f'T8 task timed out after {max_wait_s:.0f}s for {task_id} (last status: {last_status or "unknown"}).')


async def generate_openai_style_image(
    request_fn,
    provider_label,
    prompt,
    aspect_ratio,
    output_dir,
    index,
    total,
):
    tag = f'[{index + 1}/{total}] ' if total > 1 else ''
    existing = find_existing_image(output_dir, index, total, aspect_ratio=aspect_ratio)
    if existing:
        print(f'{tag}Reusing existing image: {existing}')
        return existing

    async def _generate_once():
        print(f'{tag}Submitting {provider_label} image request...')
        result = await asyncio.to_thread(request_fn, prompt, aspect_ratio)
        data = result.get('data') or []
        if not data:
            raise RetryableError(f'{tag}No image data in {provider_label} response.')

        timestamp = int(time.time() * 1000)
        suffix = f'{str(index + 1).zfill(len(str(total)))}' if total > 1 else '1'
        filepath = str(Path(output_dir) / f'image2_{suffix}_{timestamp}.png')
        temp_path = f'{filepath}.tmp'
        try:
            print(f'{tag}Saving image to {filepath}...')
            await asyncio.to_thread(save_image_result, data[0], temp_path)
            width, height = await asyncio.to_thread(
                validate_image_aspect_ratio,
                temp_path,
                aspect_ratio,
            )
            await asyncio.to_thread(os.replace, temp_path, filepath)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError:
                pass
        print(f'{tag}Image saved and validated: {filepath} ({width}x{height})')
        return filepath

    return await with_retry(_generate_once, max_retries=MAX_RETRIES, context=tag)


async def generate_single_macode(prompt, aspect_ratio, output_dir, index, total):
    return await generate_openai_style_image(
        request_macode_image_sync,
        'macode',
        prompt,
        aspect_ratio,
        output_dir,
        index,
        total,
    )


async def generate_single_t8(prompt, aspect_ratio, output_dir, index, total):
    return await generate_openai_style_image(
        request_t8_image_sync,
        't8',
        prompt,
        aspect_ratio,
        output_dir,
        index,
        total,
    )


async def generate_single_kie(prompt, aspect_ratio, output_dir, index, total):
    return await generate_openai_style_image(
        request_kie_image_sync,
        'Kie',
        prompt,
        aspect_ratio,
        output_dir,
        index,
        total,
    )


async def generate_single_apimart(prompt, aspect_ratio, output_dir, index, total):
    return await generate_openai_style_image(
        request_apimart_image_sync,
        'APIMart',
        prompt,
        aspect_ratio,
        output_dir,
        index,
        total,
    )


async def generate_single_gemini(prompt, aspect_ratio, output_dir, index, total):
    return await generate_openai_style_image(
        request_gemini_image_sync,
        'Gemini',
        prompt,
        aspect_ratio,
        output_dir,
        index,
        total,
    )



# --- Error classification ---
class RetryableError(Exception):
    """Errors worth retrying (rate-limit, server error, network)."""
    def __init__(self, message, *, is_rate_limit=False):
        super().__init__(message)
        self.is_rate_limit = is_rate_limit


class FatalError(Exception):
    """Errors that should not be retried (bad request, auth, etc)."""
    pass


def classify_error(e):
    """Return (retryable, is_rate_limit) for a given exception."""
    msg = str(e).lower()
    if isinstance(e, FatalError):
        return False, False
    if 'http 429' in msg or 'rate' in msg or 'too many' in msg:
        return True, True
    if 'http 5' in msg:
        return True, False
    # Default: treat as retryable network/transient error
    return True, False


# --- HTTP helper (synchronous, used in thread) ---
def request_sync(method, url_path, body):
    api_key = os.environ.get('RUNNINGHUB_API_KEY')
    if not api_key:
        raise FatalError('RUNNINGHUB_API_KEY not found. Set it in environment variable or .env file.')

    url = API_BASE + url_path
    payload = json.dumps(body).encode('utf-8')
    req = Request(url, data=payload, method=method)
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {api_key}')

    try:
        with urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8')
            return json.loads(data)
    except HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        if e.code == 400 or e.code == 401 or e.code == 403:
            raise FatalError(f'HTTP {e.code}: {body_text}')
        if e.code == 429:
            raise RetryableError(f'HTTP 429 (rate limited): {body_text}', is_rate_limit=True)
        # 5xx and other codes are retryable
        raise RetryableError(f'HTTP {e.code}: {body_text}')
    except json.JSONDecodeError as e:
        raise RetryableError(f'Failed to parse response: {e}')
    except Exception as e:
        raise RetryableError(str(e))


# --- Retry wrapper with exponential backoff + jitter ---
def calc_backoff(attempt, base=RETRY_BASE_DELAY_S, is_rate_limit=False):
    """Exponential backoff with jitter. Rate-limit errors get 2x longer wait."""
    multiplier = 2.0 if is_rate_limit else 1.0
    delay = base * (2 ** (attempt - 1)) * multiplier
    jitter = random.uniform(0.5, 1.5)
    return delay * jitter


async def with_retry(fn, max_retries=MAX_RETRIES, context=''):
    for attempt in range(1, max_retries + 1):
        try:
            return await fn()
        except FatalError:
            raise
        except RetryableError as e:
            if attempt == max_retries:
                raise
            delay = calc_backoff(attempt, is_rate_limit=e.is_rate_limit)
            print(f'{context}Attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay:.1f}s...')
            await asyncio.sleep(delay)
        except Exception as e:
            retryable, is_rate_limit = classify_error(e)
            if not retryable or attempt == max_retries:
                raise
            delay = calc_backoff(attempt, is_rate_limit=is_rate_limit)
            print(f'{context}Attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay:.1f}s...')
            await asyncio.sleep(delay)


# --- Step 1: Submit text-to-image task ---
def _submit_task_sync(prompt, aspect_ratio):
    res = request_sync('POST', TEXT_TO_IMAGE_PATH, {
        'prompt': prompt,
        'aspectRatio': aspect_ratio,
        'resolution': RESOLUTION,
    })
    if not res.get('taskId'):
        raise RetryableError(f'No taskId in response: {json.dumps(res)}')
    return res['taskId']


async def submit_task(prompt, aspect_ratio, context=''):
    async def _do():
        task_id = await asyncio.to_thread(_submit_task_sync, prompt, aspect_ratio)
        print(f'{context}Task submitted: {task_id}')
        return task_id
    return await with_retry(_do, max_retries=SUBMIT_MAX_RETRIES, context=context)


# --- Step 2: Poll for result ---
async def poll_result(task_id, context=''):
    poll_errors = 0

    while True:
        try:
            res = await asyncio.to_thread(
                request_sync, 'POST', QUERY_PATH, {'taskId': task_id}
            )
            # Only consecutive poll errors count toward the retry limit.
            poll_errors = 0
            status = res.get('status')

            if status == 'SUCCESS':
                results = res.get('results')
                if not results or len(results) == 0 or not results[0].get('url'):
                    raise RetryableError(f'SUCCESS but no image URL: {json.dumps(res)}')
                return results[0]

            if status == 'FAILED':
                # Signal caller to re-submit; retry count is managed by generate_single
                return {'_failed': True, 'res': res}

            # QUEUED or RUNNING
            print(f'{context}Status: {status}. Polling in {POLL_INTERVAL_S}s...')
            await asyncio.sleep(POLL_INTERVAL_S)

        except FatalError:
            raise
        except RetryableError as e:
            poll_errors += 1
            if poll_errors > POLL_MAX_RETRIES:
                raise
            delay = calc_backoff(poll_errors, is_rate_limit=e.is_rate_limit)
            print(f'{context}Poll error (retry {poll_errors}/{POLL_MAX_RETRIES}): {e}. Waiting {delay:.1f}s...')
            await asyncio.sleep(delay)


# --- Step 3: Download image ---
def download_file(url, dest_path):
    """Download file with redirect support"""
    import shutil
    from urllib.request import urlopen

    temp_path = f'{dest_path}.tmp'
    req = Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    req.add_header('Accept', 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8')
    with urlopen(req, timeout=180) as resp:
        if resp.status >= 300 and resp.status < 400:
            location = resp.headers.get('Location')
            if location:
                return download_file(location, dest_path)
        if resp.status != 200:
            raise RuntimeError(f'Download failed with status {resp.status}')
        with open(temp_path, 'wb') as f:
            shutil.copyfileobj(resp, f)
    os.replace(temp_path, dest_path)
    return dest_path


# --- Generate single image ---
async def generate_single(prompt, aspect_ratio, output_dir, index, total):
    provider = get_image_provider()
    if provider == 'gemini_image':
        return await generate_single_gemini(prompt, aspect_ratio, output_dir, index, total)
    if provider == 't8_image2':
        return await generate_single_t8(prompt, aspect_ratio, output_dir, index, total)
    if provider == 'macode_image2':
        return await generate_single_macode(prompt, aspect_ratio, output_dir, index, total)
    if provider == 'kie_image2':
        return await generate_single_kie(prompt, aspect_ratio, output_dir, index, total)
    if provider == 'apimart_image2':
        return await generate_single_apimart(prompt, aspect_ratio, output_dir, index, total)

    tag = f'[{index + 1}/{total}] ' if total > 1 else ''
    existing = find_existing_image(output_dir, index, total)
    if existing:
        print(f'{tag}Reusing existing image: {existing}')
        return existing

    submit_retries = 0
    while submit_retries <= POLL_MAX_RETRIES:
        task_id = await submit_task(prompt, aspect_ratio, context=tag)
        result = await poll_result(task_id, context=tag)

        if result.get('_failed'):
            submit_retries += 1
            if submit_retries > POLL_MAX_RETRIES:
                raise RetryableError(f'{tag}Max retries exceeded for task submission.')
            delay = calc_backoff(submit_retries)
            print(f'{tag}Re-submitting task (attempt {submit_retries}/{POLL_MAX_RETRIES}) in {delay:.1f}s...')
            await asyncio.sleep(delay)
            continue
        break

    # Download with retry
    ext = result.get('outputType', 'png')
    timestamp = int(time.time() * 1000)
    suffix = f'_{str(index + 1).zfill(len(str(total)))}' if total > 1 else ''
    filename = f'banana2_{timestamp}{suffix}.{ext}'
    filepath = str(Path(output_dir) / filename)

    async def _download():
        print(f'{tag}Downloading image to {filepath}...')
        await asyncio.to_thread(download_file, result['url'], filepath)
        print(f'{tag}Image saved: {filepath}')
        return filepath

    return await with_retry(_download, max_retries=MAX_RETRIES, context=tag)


# --- Batch runner with concurrency control + final retry for failures ---
async def run_batch(tasks, concurrency):
    semaphore = asyncio.Semaphore(concurrency)
    results = [None] * len(tasks)

    async def worker(i, task):
        async with semaphore:
            try:
                results[i] = await generate_single(
                    task['prompt'], task['aspectRatio'],
                    task['outputDir'], task['index'], task['total']
                )
            except Exception as e:
                results[i] = {'error': str(e), 'task': task, 'fatal': isinstance(e, FatalError)}

    await asyncio.gather(*(worker(i, t) for i, t in enumerate(tasks)))

    # Final retry pass: retry all failed tasks (with same concurrency limit)
    failed_indices = [
        i for i, r in enumerate(results)
        if isinstance(r, dict) and r.get('error') and not r.get('fatal')
    ]
    if failed_indices:
        print(f'\nRetrying {len(failed_indices)} failed tasks...')
        await asyncio.sleep(RETRY_BASE_DELAY_S)

        async def retry_worker(i):
            async with semaphore:
                task = results[i]['task']
                try:
                    results[i] = await generate_single(
                        task['prompt'], task['aspectRatio'],
                        task['outputDir'], task['index'], task['total']
                    )
                except Exception as e:
                    results[i] = {'error': str(e)}

        await asyncio.gather(*(retry_worker(i) for i in failed_indices))

    return results


# --- Main ---
async def main():
    load_env()
    args = sys.argv[1:]
    prompt_arg = args[0] if len(args) > 0 else ''
    aspect_ratio = args[1] if len(args) > 1 else '16:9'
    output_dir = args[2] if len(args) > 2 else os.getcwd()

    if prompt_arg.startswith('@'):
        prompt_file = Path(prompt_arg[1:])
        prompt_arg = prompt_file.read_text(encoding='utf-8')

    if not prompt_arg.strip():
        print('Error: prompt is required and cannot be empty.')
        sys.exit(1)

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Detect batch mode: prompt is a JSON-encoded array of strings, or an
    # array of task objects that carry original scene indices for resumable runs.
    prompts = None
    prompt_tasks = None
    try:
        parsed = json.loads(prompt_arg)
        if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], str):
            prompts = parsed
        elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
            prompt_tasks = []
            default_total = len(parsed)
            for i, item in enumerate(parsed):
                prompt = item.get('prompt')
                if not isinstance(prompt, str) or not prompt.strip():
                    continue
                try:
                    task_index = int(item.get('index', i))
                except (TypeError, ValueError):
                    task_index = i
                try:
                    task_total = int(item.get('total', default_total))
                except (TypeError, ValueError):
                    task_total = default_total
                prompt_tasks.append({
                    'prompt': prompt,
                    'index': max(0, task_index),
                    'total': max(1, task_total),
                })
    except (json.JSONDecodeError, ValueError):
        pass
    if not prompts and not prompt_tasks:
        prompts = [prompt_arg]

    total = len(prompt_tasks) if prompt_tasks else len(prompts)
    is_batch = total > 1
    provider = get_image_provider()
    concurrency = get_batch_concurrency()

    print(f'Image provider: {provider}')
    if is_batch:
        print(f'Batch mode: generating {total} images (concurrency: {concurrency})...')

    if prompt_tasks:
        tasks = [
            {
                'prompt': whiteboard_prompt_template + task['prompt'],
                'aspectRatio': aspect_ratio,
                'outputDir': output_dir,
                'index': task['index'],
                'total': task['total'],
            }
            for task in prompt_tasks
        ]
    else:
        tasks = [
            {
                'prompt': whiteboard_prompt_template + prompt,
                'aspectRatio': aspect_ratio,
                'outputDir': output_dir,
                'index': i,
                'total': total,
            }
            for i, prompt in enumerate(prompts)
        ]

    results = await run_batch(tasks, concurrency)

    # Summary
    succeeded = [r for r in results if isinstance(r, str)]
    failed = [r for r in results if isinstance(r, dict) and r.get('error')]
    if is_batch:
        print(f'\nBatch complete: {len(succeeded)} succeeded, {len(failed)} failed.')
    if failed:
        for f in failed:
            print(f"  Error: {f['error']}")

    # Output results as JSON for programmatic use
    print(f'\n__RESULTS__{json.dumps(results)}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
