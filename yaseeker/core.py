import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.parse import urlparse
import requests
from socid_extractor import extract

import asyncio
from typing import List, Any

from aiohttp import TCPConnector, ClientSession
import tqdm

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
}

COOKIES_FILENAME = 'cookies.txt'
REPORTS_DIRNAME = 'reports'
SESSION_TIMESTAMP_FORMAT = '%Y%m%dT%H%M%SZ'


def load_cookies(filename):
    cookies = MozillaCookieJar(filename)
    if os.path.exists(filename):
        cookies.load(ignore_discard=False, ignore_expires=False)

    return cookies


def _safe_filename(value: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', str(value)).strip('._')
    return safe or 'item'


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

        if self._is_html_response(response):
            filename = self._response_filename(request_method, request_url, 'html')
            with filename.open('w', encoding='utf-8') as f:
                f.write('<!--\n')
                f.write(self._html_comment(header_text))
                f.write('\n-->\n')
                f.write(response.text)
        else:
            filename = self._response_filename(request_method, request_url, 'raw')
            with filename.open('wb') as f:
                f.write(header_text.encode('utf-8', errors='replace'))
                f.write(b'\n\n')
                f.write(response.content)

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
            url=f'https://yandex.ru/collections/api/users/{self.identifier}',
            orig_url=f'https://yandex.ru/collections/user/{self.identifier}/'
        )

    def get_music_info(self) -> dict:
        orig_url = f'https://music.yandex.ru/users/{self.identifier}/playlists'
        referer = {'referer': orig_url}
        return self.simple_get_info_request(
            url=f'https://music.yandex.ru/handlers/library.jsx?owner={self.identifier}',
            orig_url=orig_url,
            headers_updates=referer,
        )

    def get_bugbounty_info(self) -> dict:
        return self.simple_get_info_request(f'https://yandex.ru/bugbounty/researchers/{self.identifier}/')

    def get_messenger_search_info(self) -> dict:
        url = 'https://yandex.ru/messenger/api/registry/api/'
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
        return self.simple_get_info_request(f'https://api.music.yandex.net/users/{self.identifier}')


class YaPublicUserId(IdTypeInfoAggregator):
    acceptable_fields = ('yandex_public_id', 'id',)

    @classmethod
    def validate_id(cls, name, identifier):
        # len(identifier) == 26 and
        # may be a non-standard
        return name in cls.acceptable_fields

    def get_collections_API_info(self) -> dict:
        return self.simple_get_info_request(
            url=f'https://yandex.ru/collections/api/users/{self.identifier}',
            orig_url=f'https://yandex.ru/collections/user/{self.identifier}/'
        )

    def get_reviews_info(self) -> dict:
        return self.simple_get_info_request(f'https://reviews.yandex.ru/user/{self.identifier}')

    def get_znatoki_info(self) -> dict:
        return self.simple_get_info_request(f'https://yandex.ru/q/profile/{self.identifier}/')

    def get_zen_info(self) -> dict:
        return self.simple_get_info_request(f'https://zen.yandex.ru/user/{self.identifier}')

    def get_market_info(self) -> dict:
        return self.simple_get_info_request(f'https://market.yandex.ru/user/{self.identifier}/reviews')

    def get_o_info(self) -> dict:
        return self.simple_get_info_request(f'http://o.yandex.ru/profile/{self.identifier}/')

    def get_kinopoisk_info(self) -> dict:
        return self.simple_get_info_request(f'https://www.kinopoisk.ru/user/{self.identifier}/')


class YaMessengerGuid(IdTypeInfoAggregator):
    acceptable_fields = ('yandex_messenger_guid',)

    @classmethod
    def validate_id(cls, name, identifier):
        return len(identifier) == 36 and '-' in identifier and name in cls.acceptable_fields

    def get_messenger_info(self) -> dict:
        url = 'https://yandex.ru/messenger/api/registry/api/'
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
    def __init__(self, input_data: InputData, results: List[OutputData], session_dir: str = ''):
        self.input_data = input_data
        self.results = results
        self.session_dir = session_dir

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

        # yandex setup
        cookie_file = kwargs.get('cookie_file') or COOKIES_FILENAME
        self.cookies = load_cookies(cookie_file)
        if not self.cookies:
            print(f'Cookies not found, but are required for some sites. See README to learn how to use cookies.')

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
        )

        return results


    async def process(self, input_data: List[InputData]) -> List[OutputDataList]:
        results = []
        for i in input_data:
            results.append(await self.request(i))

        return results
