from colorama import init
import csv
import termcolor
from typing import List, Optional, Tuple

from .core import OutputData, OutputDataList, REQUEST_SPECS


# use Colorama to make Termcolor work on Windows too
init()

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
            session_dir = getattr(o, 'session_dir', '')
            if session_dir:
                text += f'Reports session: {session_dir}\n'

            avatar_urls = getattr(o, 'avatar_urls', [])
            if avatar_urls:
                text += f'Possible avatars found: {len(avatar_urls)}\n'
                for avatar_url in avatar_urls:
                    text += f'Possible avatar: {avatar_url}\n'

            lead_results = [r for r in o.results if _result_has_returned_data(r)]
            text += f'Leads found: {len(lead_results)}\n'
            if not lead_results:
                text += 'No leads found.\n'

            for n, r in enumerate(lead_results):
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

        text += f'Total leads found: {total}\n'

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
        with open(self.filename, 'w', encoding="utf-8") as f:
            f.write(text)

        return f'Results were saved to file {self.filename}'


class CSVOutput(Output):
    def __init__(self, *args, **kwargs):
        self.filename = kwargs.get('filename', 'report.csv')
        super().__init__(*args, **kwargs)

    def put(self):
        if not len(self.data):
            return ''

        fields = []
        for f in self.data:
            for r in f.results:
                if not _result_has_returned_data(r):
                    continue
                fields += r.fields

        fields = list(set(fields))

        fieldnames = ['Target', 'Reports Session', 'Leads Found', 'Possible Avatars'] + [
            k.title().replace('_', ' ') for k in fields
        ]

        with open(self.filename, 'w', encoding="utf-8", newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()

            for o in self.data:
                i = o.input_data
                session_dir = getattr(o, 'session_dir', '')
                avatar_urls = getattr(o, 'avatar_urls', [])
                possible_avatars = '\n'.join(avatar_urls)
                lead_results = [r for r in o.results if _result_has_returned_data(r)]

                if not lead_results:
                    writer.writerow({
                        'Target': i,
                        'Reports Session': session_dir,
                        'Leads Found': 'No',
                        'Possible Avatars': possible_avatars,
                    })
                    continue

                for r in lead_results:
                    row = {
                        'Target': i,
                        'Reports Session': session_dir,
                        'Leads Found': 'Yes',
                        'Possible Avatars': possible_avatars,
                    }
                    for k in fields:
                        key = k.title().replace('_', ' ')
                        val = r.__dict__.get(k)
                        row[key] = val

                    writer.writerow(row)

        return f'Results were saved to file {self.filename}'
