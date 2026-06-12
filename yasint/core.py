import codecs
from html import unescape
from html.parser import HTMLParser
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.parse import urljoin, urlparse
from charset_normalizer import from_bytes
import requests
import termcolor
from socid_extractor import extract

import asyncio
from typing import Dict, List, Any, Tuple

from aiohttp import TCPConnector, ClientSession
import tqdm

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
}

COOKIES_FILENAME = 'cookies.txt'
REPORTS_DIRNAME = 'reports'
SESSION_TIMESTAMP_FORMAT = '%Y%m%dT%H%M%SZ'
HTML_BOMS = (
    (codecs.BOM_UTF32_BE, 'utf-32-be'),
    (codecs.BOM_UTF32_LE, 'utf-32-le'),
    (codecs.BOM_UTF8, 'utf-8'),
    (codecs.BOM_UTF16_BE, 'utf-16-be'),
    (codecs.BOM_UTF16_LE, 'utf-16-le'),
)

# Platform -> (HTTP method, URL template).
# NOTE: "{value}" will be replaced by the identifier being queried.
REQUEST_SPECS: Dict[str, Tuple[str, str]] = {
    "collections api": ("GET",  "https://yandex.ru/collections/api/users/{value}"),
    "music":           ("GET",  "https://music.yandex.ru/handlers/library.jsx?owner={value}"),
    "bugbounty":       ("GET",  "https://yandex.ru/bugbounty/researchers/{value}/"),
    "messenger search":("POST", "https://yandex.ru/messenger/api/registry/api/"),
    "music api":       ("GET",  "https://api.music.yandex.net/users/{value}"),
    "reviews":         ("GET",  "https://reviews.yandex.ru/user/{value}"),
    "znatoki":         ("GET",  "https://yandex.ru/q/profile/{value}/"),
    "zen":             ("GET",  "https://zen.yandex.ru/user/{value}"),
    "market":          ("GET",  "https://market.yandex.ru/user/{value}/reviews"),
    "o":               ("GET",  "http://o.yandex.ru/profile/{value}/"),
    "kinopoisk":       ("GET",  "https://www.kinopoisk.ru/user/{value}/"),
    "messenger":       ("POST", "https://yandex.ru/messenger/api/registry/api/"),
}
QUERIED_HOSTS = frozenset(
    parsed.hostname
    for parsed in (
        urlparse(template.format(value='__cookie_probe__'))
        for _, template in REQUEST_SPECS.values()
    )
    if parsed.hostname
)
AVATAR_URL_RE = re.compile(r'(?:https?:)?//avatars\.mds\.yandex\.net/[^\s"\'<>,;)]+', re.IGNORECASE)
AVATAR_HINT_RE = re.compile(r'avatar|аватар', re.IGNORECASE)
AVATAR_URL_IGNORE_PATTERNS = (
    re.compile(r'/get-realty-content/', re.IGNORECASE),
    re.compile(r'/get-realty-offers/', re.IGNORECASE),
    re.compile(r'/get-verba/', re.IGNORECASE),
	re.compile(r'/get-vertis-journal/', re.IGNORECASE),
    re.compile(r'/get-ugc/', re.IGNORECASE),
    # Yandex Market CMS / advertising creatives, favicons, banners, placeholders
    re.compile(r'/get-marketcms/', re.IGNORECASE),
    re.compile(r'/get-market-adv/', re.IGNORECASE),

    # Yandex default / placeholder avatars
    re.compile(r'/get-yapic/0/0-0(?:/|$)', re.IGNORECASE),
    re.compile(r'/get-yapic/[1-9]\d*/0[a-z0-9]*-\d+(?:/|$)', re.IGNORECASE),
	)
AVATAR_URL_ATTRS = {
    'src',
    'srcset',
    'data-src',
    'data-srcset',
    'data-original',
    'data-lazy-src',
}
AVATAR_CONTENT_TYPE_EXTENSIONS = {
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp',
    'image/svg+xml': 'svg',
}
AVATAR_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'}


def load_cookies(filename):
    cookies = MozillaCookieJar(filename)
    if os.path.exists(filename):
        cookies.load(ignore_discard=False, ignore_expires=False)

    return cookies


def _safe_filename(value: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', str(value)).strip('._')
    return safe or 'item'


def _normalise_http_url(value: str, base_url: str) -> str:
    value = unescape(str(value or '')).strip()
    if not value:
        return ''

    url = urljoin(base_url, value)
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return ''

    return url


def _avatar_url_is_ignored(url: str) -> bool:
    path = urlparse(url).path or ''
    return any(pattern.search(path) for pattern in AVATAR_URL_IGNORE_PATTERNS)


class _AvatarURLParser(HTMLParser):
    VOID_TAGS = {
        'area',
        'base',
        'br',
        'col',
        'embed',
        'hr',
        'img',
        'input',
        'link',
        'meta',
        'param',
        'source',
        'track',
        'wbr',
    }
    AVATAR_TAGS = {'img', 'source'}

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.urls = []
        self._context = []

    def handle_starttag(self, tag, attrs):
        self._handle_tag(tag, attrs, push=True)

    def handle_startendtag(self, tag, attrs):
        self._handle_tag(tag, attrs, push=False)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self._context) - 1, -1, -1):
            if self._context[index][0] == tag:
                del self._context[index:]
                break

    def _handle_tag(self, tag, attrs, push: bool):
        tag = tag.lower()
        attrs_dict = {str(k).lower(): str(v or '') for k, v in attrs}
        attr_text = ' '.join([tag] + list(attrs_dict.keys()) + list(attrs_dict.values()))
        in_avatar_context = bool(AVATAR_HINT_RE.search(attr_text)) or any(
            context for _, context in self._context
        )

        self._add_yandex_avatar_urls(attrs_dict.values())

        if in_avatar_context and tag in self.AVATAR_TAGS:
            self._add_candidate_urls(attrs_dict)

        if push and tag not in self.VOID_TAGS:
            self._context.append((tag, in_avatar_context))

    def _add_yandex_avatar_urls(self, values):
        for value in values:
            text = unescape(str(value or ''))
            for match in AVATAR_URL_RE.finditer(text):
                self._add_url(match.group(0))

    def _add_candidate_urls(self, attrs_dict):
        for name, value in attrs_dict.items():
            if name not in AVATAR_URL_ATTRS:
                continue

            for candidate in self._split_url_attribute(value):
                self._add_url(candidate)

    @staticmethod
    def _split_url_attribute(value: str):
        text = unescape(str(value or '')).strip()
        if not text:
            return []

        candidates = []
        for part in text.split(','):
            tokens = part.strip().split()
            if tokens:
                candidates.append(tokens[0])

        return candidates

    def _add_url(self, value: str):
        url = _normalise_http_url(value, self.base_url)
        if url and not _avatar_url_is_ignored(url):
            self.urls.append(url)


def _request_url(platform: str, value: str) -> str:
    return REQUEST_SPECS[platform][1].format(value=value)


def _colored_text(value: str, color: str, no_color: bool) -> str:
    if no_color:
        return value

    try:
        return termcolor.colored(value, color, force_color=True)
    except TypeError:
        return termcolor.colored(value, color)


def _cookie_matches_host(cookie, host: str) -> bool:
    cookie_domain = str(getattr(cookie, 'domain', '')).lower()
    if not cookie_domain:
        return False

    host = host.lower()
    is_domain_cookie = getattr(cookie, 'domain_initial_dot', False) or cookie_domain.startswith('.')
    cookie_domain = cookie_domain.lstrip('.')

    if is_domain_cookie:
        return host == cookie_domain or host.endswith(f'.{cookie_domain}')

    return host == cookie_domain


def _relevant_cookie_count(cookies) -> int:
    return sum(
        1
        for cookie in cookies
        if any(_cookie_matches_host(cookie, host) for host in QUERIED_HOSTS)
    )


class SessionRecorder:
    def __init__(self, root: str, target: str):
        self.timestamp = datetime.now(timezone.utc).strftime(SESSION_TIMESTAMP_FORMAT)
        session_stem = f'{self.timestamp}_{_safe_filename(target)}'
        self.session_dir = Path(root) / session_stem

        counter = 2
        while self.session_dir.exists():
            self.session_dir = Path(root) / f'{session_stem}_{counter}'
            counter += 1

        self.session_dir.mkdir(parents=True)
        self.counter = 0
        self.avatar_urls = []
        self.avatar_urls_seen = set()

    def save_response(self, method: str, url: str, response):
        for r in list(getattr(response, 'history', [])) + [response]:
            try:
                self._save_single_response(method, url, r)
            except Exception as e:
                print(f'Error while saving response for URL {url}: {e}\n')

    def save_request_error(self, method: str, url: str, error: Exception):
        try:
            filename = self._response_filename(method, url, 'error.txt')
            with filename.open('w', encoding='utf-8') as f:
                f.write(f'Request: {method} {url}\n')
                f.write(f'Error: {error}\n')
        except Exception as e:
            print(f'Error while saving request error for URL {url}: {e}\n')

    def _save_single_response(self, method: str, url: str, response):
        request = getattr(response, 'request', None)
        request_method = getattr(request, 'method', None) or method
        request_url = getattr(request, 'url', None) or getattr(response, 'url', None) or url
        header_text = self._response_header_text(request_method, request_url, response)
        is_html = self._is_html_response(response)

        if is_html:
            filename = self._response_filename(request_method, request_url, 'html')
            with filename.open('wb') as f:
                f.write(self._html_with_header_comment(response.content, header_text))
        else:
            filename = self._response_filename(request_method, request_url, 'raw')
            with filename.open('wb') as f:
                f.write(header_text.encode('utf-8', errors='replace'))
                f.write(b'\n\n')
                f.write(response.content)

        self._save_avatars_from_content(request_url, response.content, parse_html=is_html)

    def _save_avatars_from_content(self, base_url: str, content: bytes, parse_html: bool = False):
        try:
            avatar_urls = self._avatar_urls_from_content(content, base_url, parse_html=parse_html)
        except Exception as e:
            print(f'Error while detecting avatars for URL {base_url}: {e}\n')
            return

        for avatar_url in avatar_urls:
            if avatar_url in self.avatar_urls_seen:
                continue

            self.avatar_urls_seen.add(avatar_url)
            self.avatar_urls.append(avatar_url)
            self._save_avatar(avatar_url)

    def _save_avatar(self, avatar_url: str):
        if _avatar_url_is_ignored(avatar_url):
            return

        try:
            r = requests.get(avatar_url, headers=HEADERS, timeout=30)
            status_code = getattr(r, 'status_code', 0) or 0
            if status_code >= 400:
                reason = getattr(r, 'reason', '')
                raise requests.HTTPError(f'{status_code} {reason}'.rstrip())

            filename = self._response_filename('GET', avatar_url, self._avatar_file_suffix(r, avatar_url))
            body = getattr(r, 'content', b'') or b''
            if isinstance(body, str):
                body = body.encode('utf-8')

            with filename.open('wb') as f:
                f.write(body)
        except Exception as e:
            self.save_request_error('GET', avatar_url, e)
            print(f'Error while saving avatar for URL {avatar_url}: {e}\n')

    @classmethod
    def _avatar_urls_from_content(cls, content: bytes, base_url: str, parse_html: bool = False):
        text = cls._content_text(content)
        search_text = text.replace('\\/', '/')
        urls = []

        for match in AVATAR_URL_RE.finditer(search_text):
            url = _normalise_http_url(match.group(0), base_url)
            if url and not _avatar_url_is_ignored(url):
                urls.append(url)

        if parse_html:
            parser = _AvatarURLParser(base_url)
            try:
                parser.feed(text)
            except Exception:
                pass
            urls.extend(parser.urls)

        return cls._unique_urls(urls)

    @classmethod
    def _content_text(cls, content: bytes) -> str:
        bom, body, encoding = cls._html_content_parts(content)
        return (bom + body).decode(encoding, errors='replace')

    @staticmethod
    def _unique_urls(urls):
        unique = []
        seen = set()

        for url in urls:
            if url in seen:
                continue

            seen.add(url)
            unique.append(url)

        return unique

    @staticmethod
    def _avatar_file_suffix(response, avatar_url: str) -> str:
        headers = getattr(response, 'headers', {}) or {}
        content_type = headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        extension = AVATAR_CONTENT_TYPE_EXTENSIONS.get(content_type)

        if not extension:
            path_extension = Path(urlparse(avatar_url).path).suffix.lower().lstrip('.')
            if path_extension in AVATAR_IMAGE_EXTENSIONS:
                extension = path_extension

        return f'avatar.{extension or "raw"}'

    def _response_filename(self, method: str, url: str, suffix: str) -> Path:
        self.counter += 1
        parsed = urlparse(url)
        label = f'{method}_{parsed.netloc}{parsed.path}'
        if parsed.query:
            label += f'_{parsed.query}'
        label = _safe_filename(label)[:160]
        return self.session_dir / f'{self.counter:03d}_{label}.{suffix}'

    @staticmethod
    def _response_header_text(method: str, url: str, response) -> str:
        reason = response.reason or ''
        lines = [
            f'Request: {method} {url}',
            f'Status: {response.status_code} {reason}'.rstrip(),
            'Response headers:',
        ]
        lines.extend(f'{k}: {v}' for k, v in response.headers.items())
        return '\n'.join(lines)

    @staticmethod
    def _is_html_response(response) -> bool:
        content_type = response.headers.get('Content-Type', '').lower()
        if 'html' in content_type:
            return True

        body_start = response.content[:512].lstrip().lower()
        return body_start.startswith(b'<!doctype html') or body_start.startswith(b'<html')

    @classmethod
    def _html_with_header_comment(cls, content: bytes, header_text: str) -> bytes:
        bom, body, encoding = cls._html_content_parts(content)
        comment = '<!--\n' + cls._html_comment(header_text) + '\n-->\n'
        return bom + comment.encode(encoding, errors='xmlcharrefreplace') + body

    @classmethod
    def _html_content_parts(cls, content: bytes):
        for bom, encoding in HTML_BOMS:
            if content.startswith(bom):
                return bom, content[len(bom):], encoding

        return b'', content, cls._detect_html_encoding(content)

    @staticmethod
    def _detect_html_encoding(content: bytes) -> str:
        match = from_bytes(content).best()
        encoding = getattr(match, 'encoding', None)
        if not encoding:
            return 'utf-8'

        try:
            codecs.lookup(encoding)
        except LookupError:
            return 'utf-8'

        return encoding

    @staticmethod
    def _html_comment(text: str) -> str:
        return text.replace('--', '- -')


class ObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


class IdTypeInfoAggregator:
    acceptable_fields = ()

    def __init__(self, identifier: str, cookies: dict, session_recorder=None, progress=None):
        self.identifier = identifier
        self.cookies = cookies
        self.session_recorder = session_recorder
        self.progress = progress
        self.info = {}
        self.sites_results = {}

    @classmethod
    def validate_id(cls, name, identifier):
        return name in cls.acceptable_fields

    def _add_url_hits(self, count: int):
        if self.progress is not None:
            self.progress.total += count
            self.progress.refresh()

    def _finish_url_hit(self):
        if self.progress is not None:
            self.progress.update(1)

    def _save_response(self, method: str, url: str, response):
        if self.session_recorder is not None:
            self.session_recorder.save_response(method, url, response)

    def _save_request_error(self, method: str, url: str, error: Exception):
        if self.session_recorder is not None:
            self.session_recorder.save_request_error(method, url, error)

    def aggregate(self, info: dict):
        for k, v in info.items():
            if k in self.info:
                if isinstance(self.info[k], set):
                    self.info[k].add(v)
                else:
                    self.info[k] = {self.info[k], v}
            else:
                self.info[k] = v

    def simple_get_info_request(self, url: str, headers_updates: dict = None, orig_url: str = None) -> dict:
        headers = dict(HEADERS)
        headers.update(headers_updates if headers_updates else {})

        r = None
        try:
            r = requests.get(url, headers=headers, cookies=self.cookies)
        except Exception as e:
            self._save_request_error('GET', url, e)
            print(f'Error for request by URL {url}: {e}\n')
            return {}
        finally:
            if r is not None:
                self._save_response('GET', url, r)
            self._finish_url_hit()

        if '/checkcaptcha?key=' in r.text:
            info = {'Error': 'Captcha detected'}
        else:
            try:
                info = extract(r.text)
            except Exception as e:
                print(f'Error for URL {url}: {e}\n')
                info = {}

            if info:
                info['URL'] = orig_url or url
                if orig_url and url and orig_url != url:
                    info['URL_secondary'] = url

        return info

    def collect(self):
        methods = [f for f in self.__dir__() if f.startswith('get_')]
        self._add_url_hits(len(methods))

        for f in methods:
            info = getattr(self, f)()
            name = ' '.join(f.split('_')[1:-1])
            self.sites_results[name] = info
            self.aggregate(info)

    def print(self):
        for sitename, data in self.sites_results.items():
            print('[+] Yandex.' + sitename[0].upper() + sitename[1:])
            if not data:
                print('\tNot found.\n')
                continue

            if 'URL' in data:
                print(f'\tURL: {data.get("URL")}')
            for k, v in data.items():
                if k != 'URL':
                    print('\t' + k.capitalize() + ': ' + v)
            print()


class YaUsername(IdTypeInfoAggregator):
    acceptable_fields = ('username',)

    def get_collections_API_info(self) -> dict:
        return self.simple_get_info_request(
            url=_request_url('collections api', self.identifier),
            orig_url=f'https://yandex.ru/collections/user/{self.identifier}/'
        )

    def get_music_info(self) -> dict:
        orig_url = f'https://music.yandex.ru/users/{self.identifier}/playlists'
        referer = {'referer': orig_url}
        return self.simple_get_info_request(
            url=_request_url('music', self.identifier),
            orig_url=orig_url,
            headers_updates=referer,
        )

    def get_bugbounty_info(self) -> dict:
        return self.simple_get_info_request(_request_url('bugbounty', self.identifier))

    def get_messenger_search_info(self) -> dict:
        url = _request_url('messenger search', self.identifier)
        data = {"method": "search",
                "params": {"query": self.identifier, "limit": 10, "entities": ["messages", "users_and_chats"]}}
        r = None
        try:
            r = requests.post(url, headers=HEADERS, cookies=self.cookies, files={'request': (None, json.dumps(data))})
        except Exception as e:
            self._save_request_error('POST', url, e)
            print(f'Error for request by URL {url}: {e}\n')
            return {}
        finally:
            if r is not None:
                self._save_response('POST', url, r)
            self._finish_url_hit()

        info = extract(r.text)
        if info and info.get('yandex_messenger_guid'):
            info['URL'] = f'https://yandex.ru/chat#/user/{info["yandex_messenger_guid"]}'
        return info

    def get_music_API_info(self) -> dict:
        return self.simple_get_info_request(_request_url('music api', self.identifier))


class YaPublicUserId(IdTypeInfoAggregator):
    acceptable_fields = ('yandex_public_id', 'id',)

    @classmethod
    def validate_id(cls, name, identifier):
        # len(identifier) == 26 and
        # may be a non-standard
        return name in cls.acceptable_fields

    def get_collections_API_info(self) -> dict:
        return self.simple_get_info_request(
            url=_request_url('collections api', self.identifier),
            orig_url=f'https://yandex.ru/collections/user/{self.identifier}/'
        )

    def get_reviews_info(self) -> dict:
        return self.simple_get_info_request(_request_url('reviews', self.identifier))

    def get_znatoki_info(self) -> dict:
        return self.simple_get_info_request(_request_url('znatoki', self.identifier))

    def get_zen_info(self) -> dict:
        return self.simple_get_info_request(_request_url('zen', self.identifier))

    def get_market_info(self) -> dict:
        return self.simple_get_info_request(_request_url('market', self.identifier))

    def get_o_info(self) -> dict:
        return self.simple_get_info_request(_request_url('o', self.identifier))

    def get_kinopoisk_info(self) -> dict:
        return self.simple_get_info_request(_request_url('kinopoisk', self.identifier))


class YaMessengerGuid(IdTypeInfoAggregator):
    acceptable_fields = ('yandex_messenger_guid',)

    @classmethod
    def validate_id(cls, name, identifier):
        return len(identifier) == 36 and '-' in identifier and name in cls.acceptable_fields

    def get_messenger_info(self) -> dict:
        url = _request_url('messenger', self.identifier)
        data = {"method": "get_users_data", "params": {"guids": [self.identifier]}}
        r = None
        try:
            r = requests.post(url, headers=HEADERS, cookies=self.cookies, files={'request': (None, json.dumps(data))})
        except Exception as e:
            self._save_request_error('POST', url, e)
            print(f'Error for request by URL {url}: {e}\n')
            return {}
        finally:
            if r is not None:
                self._save_response('POST', url, r)
            self._finish_url_hit()

        info = extract(r.text)
        if info:
            info['URL'] = f'https://yandex.ru/chat#/user/{self.identifier}'
        return info


def crawl(user_data: dict, output: dict, cookies: dict = None, checked_values: list = None, session_recorder=None, progress=None):
    entities = (YaUsername, YaPublicUserId, YaMessengerGuid)
    if cookies is None:
        cookies = {}
    if checked_values is None:
        checked_values = []

    for k, v in user_data.items():
        values = list(v) if isinstance(v, set) else [v]
        for value in values:
            if value in checked_values:
                continue

            for e in entities:
                if not e.validate_id(k, value):
                    continue

                checked_values.append(value)

                # print(f'[*] Get info by {k} `{value}`...\n')
                entity_obj = e(value, cookies, session_recorder=session_recorder, progress=progress)
                entity_obj.collect()
                # entity_obj.print()

                output[entity_obj.identifier] = entity_obj.sites_results

                crawl(entity_obj.info, output, cookies, checked_values, session_recorder=session_recorder, progress=progress)

    return output


class InputData:
    def __init__(self, value: str):
        self.value = value.split('@')[0]
        if len(self.value) == 26:
            self.identifier_type = 'yandex_public_id'
        else:
            self.identifier_type = 'username'

        print(f'Identifier "{self.value}" recognized as a {self.identifier_type}')

    def __str__(self):
        return f'{self.value} ({self.identifier_type})'

    def __repr__(self):
        return f'{self.value} ({self.identifier_type})'


class OutputData:
    def __init__(self, value, dict_data, error):
        self.value = value
        self.error = error

        # postprocess
        if 'image' in dict_data:
            dict_data['image'] = dict_data['image'].replace('islands-200', 'islands-300')  # increase photo size
        self.__dict__.update(dict_data)

    @property
    def fields(self):
        fields = list(self.__dict__.keys())
        fields.remove('error')

        return fields

    def __str__(self):
        error = ''
        if self.error:
            error = f' (error: {str(self.error)}'

        result = ''

        for field in self.fields:
            field_pretty_name = field.title().replace('_', ' ')
            value = self.__dict__.get(field)
            if value:
                result += f'{field_pretty_name}: {str(value)}\n'

        result += f'{error}'
        return result


class OutputDataList:
    def __init__(
        self,
        input_data: InputData,
        results: List[OutputData],
        session_dir: str = '',
        avatar_urls: List[str] = None,
    ):
        self.input_data = input_data
        self.results = results
        self.session_dir = session_dir
        self.avatar_urls = avatar_urls or []

    def __repr__(self):
        return f'Target {self.input_data}:\n' + '--------\n'.join(map(str, self.results))


class Processor:
    def __init__(self, *args, **kwargs):
        from aiohttp_socks import ProxyConnector

        # make http client session
        proxy = kwargs.get('proxy')
        self.proxy = proxy
        if proxy:
            connector = ProxyConnector.from_url(proxy, ssl=False)
        else:
            connector = TCPConnector(ssl=False)

        self.session = ClientSession(
            connector=connector, trust_env=True
        )
        self.no_progressbar = kwargs.get('no_progressbar', False)
        no_color = kwargs.get('no_color', False)

        # yandex setup
        cookie_file = kwargs.get('cookie_file') or COOKIES_FILENAME
        self.cookies = load_cookies(cookie_file)
        if self.cookies:
            cookie_count = _relevant_cookie_count(self.cookies)
            if cookie_count:
                cookie_word = 'cookie' if cookie_count == 1 else 'cookies'
                message = f'Cookies loaded from {cookie_file} for queried domains: {cookie_count} {cookie_word}.'
                print(_colored_text(message, 'green', no_color))
            else:
                message = f'Cookies loaded from {cookie_file}, but none match queried domains.'
                print(_colored_text(message, 'yellow', no_color))
        else:
            message = 'Cookies not found, but are required for some sites. See README to learn how to use cookies.'
            print(_colored_text(message, 'yellow', no_color))

    async def close(self):
        await self.session.close()


    async def request(self, input_data: InputData) -> OutputDataList:
        data = []
        result = None
        error = None
        session_recorder = SessionRecorder(REPORTS_DIRNAME, input_data.value)
        progress = None

        if not self.no_progressbar:
            progress = tqdm.tqdm(
                total=0,
                desc=f'Session {session_recorder.timestamp} {input_data.value}',
                unit='hit',
            )

        try:
            identifier = {input_data.identifier_type: input_data.value}
            output_data = crawl(
                identifier,
                {},
                cookies=self.cookies,
                session_recorder=session_recorder,
                progress=progress,
            )

            for ident, result in output_data.items():
                for platform, fields in result.items():
                    platform = platform.title().replace('_', ' ')
                    fields = fields or {}
                    fields.update({'platform': platform})

                    od = OutputData(ident, fields, error)
                    data.append(od)

        except Exception as e:
            logging.error(e, exc_info=True)
            error = e
        finally:
            if progress is not None:
                progress.close()

        results = OutputDataList(
            input_data,
            data,
            session_dir=str(session_recorder.session_dir.resolve()),
            avatar_urls=list(getattr(session_recorder, 'avatar_urls', [])),
        )

        return results


    async def process(self, input_data: List[InputData]) -> List[OutputDataList]:
        results = []
        for i in input_data:
            results.append(await self.request(i))

        return results
