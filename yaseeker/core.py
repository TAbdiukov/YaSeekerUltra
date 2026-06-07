import asyncio
import json
import logging
import os
import sys
from http.cookiejar import MozillaCookieJar
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from aiohttp import ClientSession, TCPConnector
from socid_extractor import extract

from .executor import AsyncioProgressbarQueueExecutor, AsyncioSimpleExecutor

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/143.0.0.0 Safari/537.36'
    ),
}

COOKIES_FILENAME = 'cookies.txt'
ARTIFACT_ALIASES = {
    'id': 'yandex_public_id',
    'login': 'username',
}
RESULT_METADATA_FIELDS = {
    'artifact_type',
    'artifact_depth',
    'artifact_seed',
    'artifact_query_order',
    'artifact_platforms_checked',
    'artifact_platforms_with_data',
    'discovered_from',
}


def canonical_artifact_type(name: str) -> str:
    return ARTIFACT_ALIASES.get((name or '').strip().lower(), (name or '').strip().lower())


def normalize_artifact_value(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ''
    return str(value).strip()


def iter_artifact_values(value: Any) -> Iterable[Any]:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield item
        return
    yield value


def artifact_key(identifier_type: str, value: Any) -> Tuple[str, str]:
    return canonical_artifact_type(identifier_type), normalize_artifact_value(value)


def pretty_platform_name(name: str) -> str:
    return (name or '').title().replace('_', ' ')


def load_cookies(filename):
    cookies = {}
    if os.path.exists(filename):
        cookies_obj = MozillaCookieJar(filename)
        cookies_obj.load(ignore_discard=False, ignore_expires=False)

        for domain in cookies_obj._cookies.values():
            for cookie_dict in list(domain.values()):
                for _, cookie in cookie_dict.items():
                    cookies[cookie.name] = cookie.value

    return cookies


class ObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


class ArtifactData:
    def __init__(self, identifier_type: str, value: str, depth: int = 0, seed: bool = False):
        self.identifier_type = canonical_artifact_type(identifier_type)
        self.value = normalize_artifact_value(value)
        self.depth = depth
        self.seed = seed
        self.queried = False
        self.query_order: Optional[int] = None
        self.platforms_checked = 0
        self.platforms_with_data = 0
        self.discovered_from: List[Dict[str, str]] = []
        self._discovered_from_keys = set()

    @property
    def key(self) -> Tuple[str, str]:
        return self.identifier_type, self.value

    @property
    def label(self) -> str:
        return f'{self.identifier_type}: {self.value}'

    def add_source(self, source_type: str, source_value: str, platform: str, field: str):
        source = {
            'source_type': canonical_artifact_type(source_type),
            'source_value': normalize_artifact_value(source_value),
            'platform': pretty_platform_name(platform),
            'field': field,
        }
        dedupe_key = tuple(source.values())
        if dedupe_key in self._discovered_from_keys:
            return
        self._discovered_from_keys.add(dedupe_key)
        self.discovered_from.append(source)

    def discovered_from_text(self) -> str:
        if self.seed:
            return 'seed input'
        if not self.discovered_from:
            return ''
        return '; '.join(
            (
                f'{item["source_type"]}: {item["source_value"]} '
                f'-> {item["platform"]}.{item["field"]}'
            )
            for item in self.discovered_from
        )


class DeepSearchResult:
    def __init__(self):
        self._artifacts: Dict[Tuple[str, str], ArtifactData] = {}
        self._artifact_order: List[Tuple[str, str]] = []
        self.results: Dict[Tuple[str, str], Dict[str, dict]] = {}

    def add_artifact(self, artifact: ArtifactData):
        if artifact.key in self._artifacts:
            return
        self._artifacts[artifact.key] = artifact
        self._artifact_order.append(artifact.key)

    def get_artifact(self, identifier_type: str, value: str) -> Optional[ArtifactData]:
        return self._artifacts.get(artifact_key(identifier_type, value))

    @property
    def artifacts(self) -> List[ArtifactData]:
        return [self._artifacts[key] for key in self._artifact_order]

    def legacy_output(self) -> Dict[str, Dict[str, dict]]:
        output = {}
        for artifact in self.artifacts:
            output[artifact.value] = self.results.get(artifact.key, {})
        return output


class IdTypeInfoAggregator:
    acceptable_fields = ()

    def __init__(self, identifier: str, cookies: dict):
        self.identifier = identifier
        self.cookies = cookies
        self.info = {}
        self.sites_results = {}

    @classmethod
    def validate_id(cls, name, identifier):
        identifier = normalize_artifact_value(identifier)
        return bool(identifier) and canonical_artifact_type(name) in cls.acceptable_fields

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
        try:
            r = requests.get(url, headers=headers, cookies=self.cookies)
        except Exception as e:
            print(f'Error for request by URL {url}: {e}\n')
            return {}

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
        for f in self.__dir__():
            if f.startswith('get_'):
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
                    print('\t' + k.capitalize() + ': ' + str(v))
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
        data = {
            'method': 'search',
            'params': {
                'query': self.identifier,
                'limit': 10,
                'entities': ['messages', 'users_and_chats'],
            },
        }
        r = requests.post(url, headers=HEADERS, cookies=self.cookies, files={'request': (None, json.dumps(data))})
        info = extract(r.text)
        if info and info.get('yandex_messenger_guid'):
            info['URL'] = f'https://yandex.ru/chat#/user/{info["yandex_messenger_guid"]}'
        return info

    def get_music_API_info(self) -> dict:
        return self.simple_get_info_request(f'https://api.music.yandex.net/users/{self.identifier}')


class YaPublicUserId(IdTypeInfoAggregator):
    acceptable_fields = ('yandex_public_id',)

    @classmethod
    def validate_id(cls, name, identifier):
        # Non-standard public IDs are still useful in practice, so only type-check here.
        return super().validate_id(name, identifier)

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
        identifier = normalize_artifact_value(identifier)
        return (
            super().validate_id(name, identifier)
            and len(identifier) == 36
            and '-' in identifier
        )

    def get_messenger_info(self) -> dict:
        url = 'https://yandex.ru/messenger/api/registry/api/'
        data = {'method': 'get_users_data', 'params': {'guids': [self.identifier]}}
        r = requests.post(url, headers=HEADERS, cookies=self.cookies, files={'request': (None, json.dumps(data))})
        info = extract(r.text)
        if info:
            info['URL'] = f'https://yandex.ru/chat#/user/{self.identifier}'
        return info


def deep_crawl(user_data: dict, cookies: dict = None) -> DeepSearchResult:
    entities = (YaUsername, YaPublicUserId, YaMessengerGuid)
    if cookies is None:
        cookies = {}

    deep_results = DeepSearchResult()
    queued = set()
    checked = set()
    queue: List[Tuple[str, str]] = []

    def enqueue(identifier_type: str, value: Any, depth: int = 0, seed: bool = False, source: dict = None):
        item_type, item_value = artifact_key(identifier_type, value)
        if not item_type or not item_value:
            return None
        if not any(entity.validate_id(item_type, item_value) for entity in entities):
            return None

        artifact = deep_results.get_artifact(item_type, item_value)
        if artifact is None:
            artifact = ArtifactData(item_type, item_value, depth=depth, seed=seed)
            deep_results.add_artifact(artifact)
        else:
            artifact.depth = min(artifact.depth, depth)
            artifact.seed = artifact.seed or seed

        if source:
            source_key = artifact_key(source.get('source_type'), source.get('source_value'))
            if source_key != artifact.key:
                artifact.add_source(
                    source_type=source.get('source_type', ''),
                    source_value=source.get('source_value', ''),
                    platform=source.get('platform', ''),
                    field=source.get('field', ''),
                )

        if artifact.key not in queued and artifact.key not in checked:
            queue.append(artifact.key)
            queued.add(artifact.key)
        return artifact

    for field_name, field_values in user_data.items():
        for field_value in iter_artifact_values(field_values):
            enqueue(field_name, field_value, depth=0, seed=True)

    query_order = 0
    while queue:
        current_key = queue.pop(0)
        checked.add(current_key)
        current_type, current_value = current_key
        artifact = deep_results.get_artifact(current_type, current_value)
        if artifact is None:
            continue

        for entity in entities:
            if not entity.validate_id(current_type, current_value):
                continue

            entity_obj = entity(current_value, cookies)
            entity_obj.collect()
            query_order += 1

            artifact.queried = True
            artifact.query_order = query_order
            artifact.platforms_checked = len(entity_obj.sites_results)
            artifact.platforms_with_data = sum(1 for data in entity_obj.sites_results.values() if data)
            deep_results.results[artifact.key] = entity_obj.sites_results

            for platform_name, info in entity_obj.sites_results.items():
                for result_field, result_values in (info or {}).items():
                    if canonical_artifact_type(result_field) not in ('username', 'yandex_public_id', 'yandex_messenger_guid'):
                        continue

                    for candidate in iter_artifact_values(result_values):
                        enqueue(
                            result_field,
                            candidate,
                            depth=artifact.depth + 1,
                            source={
                                'source_type': artifact.identifier_type,
                                'source_value': artifact.value,
                                'platform': platform_name,
                                'field': result_field,
                            },
                        )
            break

    return deep_results


def crawl(user_data: dict, output: dict = None, cookies: dict = None, checked_values: list = None):
    del output, checked_values
    return deep_crawl(user_data, cookies=cookies).legacy_output()


class InputData:
    def __init__(self, value: str):
        self.original_value = value.strip()
        self.value = self.original_value.split('@')[0]
        if len(self.value) == 36 and '-' in self.value:
            self.identifier_type = 'yandex_messenger_guid'
        elif len(self.value) == 26:
            self.identifier_type = 'yandex_public_id'
        else:
            self.identifier_type = 'username'
        logging.debug('Identifier "%s" recognized as %s', self.value, self.identifier_type)

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
    def __init__(self, input_data: InputData, results: List[OutputData], artifacts: List[ArtifactData] = None):
        self.input_data = input_data
        self.results = results
        self.artifacts = artifacts or []

    def __repr__(self):
        return f'Target {self.input_data}:\n' + '--------\n'.join(map(str, self.results))


class Processor:
    def __init__(self, *args, **kwargs):
        from aiohttp_socks import ProxyConnector

        # make http client session
        proxy = kwargs.get('proxy')
        timeout = kwargs.get('timeout')
        self.proxy = proxy
        if proxy:
            connector = ProxyConnector.from_url(proxy, ssl=False)
        else:
            connector = TCPConnector(ssl=False)
        self.session = ClientSession(
            connector=connector,
            trust_env=True
        )
        executor_kwargs = {}
        if timeout is not None:
            executor_kwargs['timeout'] = timeout
        if kwargs.get('no_progressbar'):
            self.executor = AsyncioSimpleExecutor(**executor_kwargs)
        else:
            self.executor = AsyncioProgressbarQueueExecutor(**executor_kwargs)

        # yandex setup
        cookie_file = kwargs.get('cookie_file') or COOKIES_FILENAME
        self.cookies = load_cookies(cookie_file)
        if not self.cookies:
            print('Cookies not found, but are required for some sites.\nSee README to learn how to use cookies.')

    async def close(self):
        await self.session.close()

    async def request(self, input_data: InputData) -> OutputDataList:
        data = []
        error = None
        artifacts: List[ArtifactData] = []
        try:
            identifier = {input_data.identifier_type: input_data.value}
            deep_results = deep_crawl(identifier, cookies=self.cookies)
            artifacts = deep_results.artifacts
            for artifact in artifacts:
                result = deep_results.results.get(artifact.key, {})
                for platform, fields in result.items():
                    row = dict(fields or {})
                    row.update(
                        {
                            'platform': pretty_platform_name(platform),
                            'artifact_type': artifact.identifier_type,
                            'artifact_depth': artifact.depth,
                            'artifact_seed': artifact.seed,
                            'artifact_query_order': artifact.query_order,
                            'artifact_platforms_checked': artifact.platforms_checked,
                            'artifact_platforms_with_data': artifact.platforms_with_data,
                            'discovered_from': artifact.discovered_from_text(),
                        }
                    )
                    data.append(OutputData(artifact.value, row, error))
        except Exception as e:
            logging.error(e, exc_info=True)
            error = e
        results = OutputDataList(input_data, data, artifacts=artifacts)
        return results

    async def process(self, input_data: List[InputData]) -> List[OutputDataList]:
        tasks = [
            (
                self.request,  # func
                [i],  # args
                {}  # kwargs
            ) for i in input_data
        ]
        results = await self.executor.run(tasks)
        return results
