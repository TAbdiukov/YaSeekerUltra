import csv
from typing import Dict, List, Optional, Tuple

import termcolor
from colorama import init

from .core import OutputData, OutputDataList, RESULT_METADATA_FIELDS


# use Colorama to make Termcolor work on Windows too
init()

# Platform -> (HTTP method, URL template).
# NOTE: "{value}" will be replaced by the identifier printed in the entry.
REQUEST_SPECS: Dict[str, Tuple[str, str]] = {
    "collections api": ("GET", "https://yandex.ru/collections/api/users/{value}"),
    "music": ("GET", "https://music.yandex.ru/handlers/library.jsx?owner={value}"),
    "bugbounty": ("GET", "https://yandex.ru/bugbounty/researchers/{value}/"),
    "messenger search": ("POST", "https://yandex.ru/messenger/api/registry/api/"),
    "music api": ("GET", "https://api.music.yandex.net/users/{value}"),
    "reviews": ("GET", "https://reviews.yandex.ru/user/{value}"),
    "znatoki": ("GET", "https://yandex.ru/q/profile/{value}/"),
    "zen": ("GET", "https://zen.yandex.ru/user/{value}"),
    "market": ("GET", "https://market.yandex.ru/user/{value}/reviews"),
    "o": ("GET", "http://o.yandex.ru/profile/{value}/"),
    "kinopoisk": ("GET", "https://www.kinopoisk.ru/user/{value}/"),
    "messenger": ("POST", "https://yandex.ru/messenger/api/registry/api/"),
}
ARTIFACT_COLORS = {
    'username': 'cyan',
    'yandex_public_id': 'magenta',
    'yandex_messenger_guid': 'blue',
}


def _normalize_platform(name: str) -> str:
    # "Collections Api" -> "collections api"
    return " ".join((name or "").lower().split())


def _platform_request(platform: str, value: str) -> Optional[Tuple[str, str]]:
    spec = REQUEST_SPECS.get(_normalize_platform(platform))
    if not spec:
        return None
    method, template = spec
    return method, template.format(value=value)


def _result_has_returned_data(r: OutputData) -> bool:
    """
    True only when this platform entry actually returned extracted data.
    Entries that only have artifact metadata + Platform are treated as "no data".
    """
    ignore = {"value", "platform", "error"} | set(RESULT_METADATA_FIELDS)
    for k, v in r.__dict__.items():
        if k in ignore:
            continue
        if v is None:
            continue
        # empty string/container => no useful data
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, (list, dict, set, tuple)) and len(v) == 0:
            continue
        return True
    return False


class Output:
    def __init__(self, data: OutputDataList, *args, **kwargs):
        self.data = data

    def put(self):
        pass


class PlainOutput(Output):
    def __init__(self, *args, **kwargs):
        self.is_colored = kwargs.get('colored', True)
        super().__init__(*args, **kwargs)

    def colored(self, val, color):
        if not self.is_colored:
            return str(val)
        return termcolor.colored(str(val), color)

    def artifact_label(self, identifier_type: str, value: str) -> str:
        color = ARTIFACT_COLORS.get(identifier_type, 'white')
        return self.colored(f'{identifier_type}: {value}', color)

    def result_groups(self, output_data: OutputDataList):
        groups = {}
        for result in output_data.results:
            key = (result.__dict__.get('artifact_type', ''), result.value)
            groups.setdefault(key, []).append(result)
        return groups

    def visible_result_fields(self, result: OutputData) -> List[str]:
        return [
            field_name
            for field_name in result.fields
            if field_name not in RESULT_METADATA_FIELDS and field_name not in ('platform', 'value')
        ]

    def put(self):
        text = ''
        total_hits = 0
        olist = self.data

        for o in olist:
            i = o.input_data
            groups = self.result_groups(o)
            artifact_hits = sum(1 for r in o.results if _result_has_returned_data(r))
            total_hits += artifact_hits

            text += f'Target: {self.colored(str(i), "green")}\n'
            text += f'Artifacts discovered: {len(o.artifacts)}\n'
            text += f'Platform hits: {artifact_hits}/{len(o.results)}\n'

            if o.artifacts:
                text += self.colored('Artifacts:', 'cyan') + '\n'
                for index, artifact in enumerate(o.artifacts, start=1):
                    origin = self.colored('seed', 'green') if artifact.seed else self.colored('auto', 'yellow')
                    status = self.colored('queried', 'green') if artifact.queried else self.colored('pending', 'red')
                    text += (
                        f'  {index}) {origin} {status} '
                        f'depth={artifact.depth} '
                        f'{self.artifact_label(artifact.identifier_type, artifact.value)}\n'
                    )
                    if artifact.discovered_from:
                        for source in artifact.discovered_from:
                            text += (
                                '      via '
                                f'{self.artifact_label(source["source_type"], source["source_value"])} '
                                f'-> {self.colored(source["platform"], "yellow")}.{source["field"]}\n'
                            )
                text += '\n'

            text += self.colored('Detailed results:', 'cyan') + '\n'
            for index, artifact in enumerate(o.artifacts, start=1):
                group_key = (artifact.identifier_type, artifact.value)
                results = groups.get(group_key, [])
                found_count = sum(1 for result in results if _result_has_returned_data(result))
                text += f'{index}) {self.artifact_label(artifact.identifier_type, artifact.value)}\n'
                text += f'   Platforms with data: {found_count}/{len(results)}\n'
                if artifact.discovered_from_text():
                    text += f'   Discovered from: {artifact.discovered_from_text()}\n'
                for platform_index, result in enumerate(results, start=1):
                    platform = result.__dict__.get('platform', '') or ''
                    has_data = _result_has_returned_data(result)
                    status = self.colored('found', 'green') if has_data else self.colored('not found', 'red')
                    text += f'   {platform_index}) {self.colored(platform, "yellow")} [{status}]\n'

                    visible_fields = self.visible_result_fields(result)
                    printed_fields = 0
                    for field_name in visible_fields:
                        value = result.__dict__.get(field_name)
                        if value is None:
                            continue
                        if isinstance(value, str) and not value.strip():
                            continue
                        if isinstance(value, (list, dict, set, tuple)) and len(value) == 0:
                            continue
                        key = field_name.title().replace('_', ' ')
                        text += f'      {self.colored(key, "yellow")}: {value}\n'
                        printed_fields += 1

                    if not printed_fields:
                        text += '      No data returned.\n'
                    text += '\n'

            text += '-' * 30 + '\n'

        text += f'Total platform hits: {total_hits}\n'

        # After the summary, show request URL + request type (GET/POST) per entry.
        req_lines: List[Tuple[str, str, str, str, str]] = []
        seen = set()

        for o in olist:
            for r in o.results:
                if not _result_has_returned_data(r):
                    continue
                platform = r.__dict__.get('platform', '') or ''
                artifact_type = r.__dict__.get('artifact_type', '') or ''

                req = _platform_request(platform, r.value)
                if req:
                    method, url = req
                else:
                    # Fallback: if platform is unknown but we still have a URL in the extracted data.
                    # We don't know the real method here; assume GET only for display purposes.
                    url = (
                        r.__dict__.get('URL_secondary')
                        or r.__dict__.get('URL')
                        or r.__dict__.get('url')
                        or ''
                    )
                    method = 'GET' if url else ''

                if method and url:
                    key = (artifact_type, r.value, platform, method, url)
                    if key in seen:
                        continue
                    seen.add(key)
                    req_lines.append(key)

        if req_lines:
            text += '\n' + self.colored('Requests:', 'cyan') + '\n'
            for artifact_type, value, platform, method, url in req_lines:
                text += (
                    f'{self.artifact_label(artifact_type, value)} '
                    f'-> {self.colored(platform, "yellow")}: '
                    f'{self.colored(method, "magenta")} '
                    f'{self.colored(url, "green")}\n'
                )

        return text


class TXTOutput(PlainOutput):
    def __init__(self, *args, **kwargs):
        self.filename = kwargs.get('filename', 'report.txt')
        super().__init__(*args, **kwargs)
        self.is_colored = False

    def put(self):
        text = super().put()
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(text)

        return f'Results were saved to file {self.filename}'


class CSVOutput(Output):
    def __init__(self, *args, **kwargs):
        self.filename = kwargs.get('filename', 'report.csv')
        super().__init__(*args, **kwargs)

    def put(self):
        if not len(self.data) or not len(self.data[0].results):
            return ''

        fields = []
        for output_data in self.data:
            for result in output_data.results:
                fields += result.fields

        preferred_prefix = ['value', 'artifact_type', 'platform', 'discovered_from']
        unique_fields = []
        seen = set()
        for field_name in preferred_prefix + sorted(set(fields)):
            if field_name in seen:
                continue
            seen.add(field_name)
            unique_fields.append(field_name)

        fieldnames = ['Target'] + [field_name.title().replace('_', ' ') for field_name in unique_fields]

        with open(self.filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()

            for output_data in self.data:
                for result in output_data.results:
                    row = {'Target': output_data.input_data}
                    for field_name in unique_fields:
                        key = field_name.title().replace('_', ' ')
                        row[key] = result.__dict__.get(field_name)
                    writer.writerow(row)

        return f'Results were saved to file {self.filename}'
