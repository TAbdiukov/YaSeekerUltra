from colorama import init
import csv
import termcolor
from typing import Dict, List, Optional, Tuple

from .core import OutputData, OutputDataList


# use Colorama to make Termcolor work on Windows too
init()

# Platform -> (HTTP method, URL template).
# NOTE: "{value}" will be replaced by the identifier printed in the entry.
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
    Entries that only have Value + Platform (and maybe error) are treated as "no data".
    """
    ignore = {"value", "platform", "error"}
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
            return val

        return termcolor.colored(val, color)

    def put(self):
        text = ''
        total = 0
        olist = self.data

        for o in olist:
            i = o.input_data

            text += f'Target: {self.colored(str(i), "green")}\n'
            text += f'Results found: {len(o.results)}\n'

            for n, r in enumerate(o.results):
                text += f'{n+1}) '
                total += 1

                for k in r.fields:
                    key = k.title().replace('_', ' ')
                    val = r.__dict__.get(k)
                    if val is None:
                        val = ''

                    text += f'{self.colored(key, "yellow")}: {val}\n'

                text += '\n'

            text += '-'*30 + '\n'

        text += f'Total found: {total}\n'

        # After the summary, show request URL + request type (GET/POST) per entry.
        req_lines: List[Tuple[str, str, str]] = []
        seen = set()

        for o in olist:
            for r in o.results:
                if not _result_has_returned_data(r):
                    continue
                platform = r.__dict__.get("platform", "") or ""

                req = _platform_request(platform, r.value)
                if req:
                    method, url = req
                else:
                    # Fallback: if platform is unknown but we still have a URL in the extracted data.
                    # We don't know the real method here; assume GET only for display purposes.
                    url = (
                        r.__dict__.get("URL_secondary")
                        or r.__dict__.get("URL")
                        or r.__dict__.get("url")
                        or ""
                    )
                    method = "GET" if url else ""

                if method and url:
                    key = (platform, method, url)
                    if key in seen:
                        continue
                    seen.add(key)
                    req_lines.append(key)

        if req_lines:
            text += "\n" + self.colored("Requests:", "cyan") + "\n"
            for platform, method, url in req_lines:
                text += (
                    f'{self.colored(platform, "yellow")}: '
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
        with open(self.filename, 'w') as f:
            f.write(text)

        return f'Results were saved to file {self.filename}'


class CSVOutput(Output):
    def __init__(self, *args, **kwargs):
        self.filename = kwargs.get('filename', 'report.csv')
        super().__init__(*args, **kwargs)

    def put(self):
        if not len(self.data) and not len(self.data[0].results):
            return ''

        fields = []
        for f in self.data:
            for r in f.results:
                fields += r.fields

        fields = list(set(fields))

        fieldnames = ['Target'] + [k.title().replace('_', ' ') for k in fields]

        with open(self.filename, 'w') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()

            for o in self.data:
                i = o.input_data
                row = {'Target': i}

                for r in o.results:
                    for k in fields:
                        key = k.title().replace('_', ' ')
                        val = r.__dict__.get(k)
                        row[key] = val

                    writer.writerow(row)

        return f'Results were saved to file {self.filename}'
