# YaSINT

[![GitHub](https://img.shields.io/badge/GitHub-TAbdiukov/YaSINT-black?logo=github)](https://github.com/TAbdiukov/YaSINT)
[![PyPI Version](https://img.shields.io/pypi/v/YaSINT.svg)](https://pypi.org/project/YaSINT) 
![License](https://img.shields.io/github/license/TAbdiukov/YaSINT)

[![buymeacoffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/tabdiukov)

YaSINT is a command line OSINT toolkit for looking up public Yandex account information by username, email address, or Yandex public ID.

It is a greatly updated package based on the original YaSeeker project. YaSINT is now intended to be installed as a Python package and run with a command, although it can still be run directly from a source checkout.

## Artifacts

Depending on what public Yandex pages and APIs return, YaSINT may find:

* full name;
* profile photo or other possible avatar URLs;
* gender;
* Yandex UID;
* Yandex public ID;
* linked social accounts;
* public activity information;
* account flags, such as verified, banned, deleted, restricted, or business status.

Some services return useful information only when valid Yandex cookies are
provided. See [Cookies](#cookies).

## Installation

Python 3.8 or newer is required.

Install from PyPI:

```bash
python -m pip install yasint
```

If you already downloaded the source code, install it from the project directory:

```bash
python -m pip install .
```

After installation, the `yasint` command should be available:

```bash
yasint --version
```

If you do not want to install the package, you can run it from the source
directory instead:

```bash
python -m pip install -r requirements.txt
python -m yasint login
```

## Usage

Give YaSINT one or more targets:

```bash
yasint TARGET
```

Examples:

```bash
yasint login
yasint login@yandex.ru
yasint c48fhxw0qppa50289r5c9ku4k4
```

The tool recognises the target type automatically. Email addresses
are supported. A 26-character value is treated as a Yandex public ID.

For many targets, put one target per line in a text file:

```bash
yasint --target-list targets.txt
```

## Results

For every target, YaSINT creates a per-session folder under `reports/`.
The folder name contains a UTC timestamp and the target value.

```text
reports/20260101T120000Z_login/
```

The session folder keeps the evidence collected during the run, including saved
responses where possible and auxiliary TXT/CSV reports. The console output gives
you the human-readable summary.

You can also write your own report files:

```bash
yasint login -oT report.txt -oC report.csv
```

A `No leads found` result means the checked sources did not return useful
profile data for that target. It does not prove that the account does not exist.

## Cookies

Some Yandex services require cookies before they return useful API responses.
YaSINT can read browser cookies exported in Netscape `cookies.txt` format.

1. Log in to Yandex in your browser.
2. Export your Yandex cookies as `cookies.txt`  ([Chrome](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc), [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)).
3. Put `cookies.txt` in the directory where you run YaSINT.
4. Run YaSINT normally.

You can also pass a custom cookie file path:

```bash
yasint login --cookie-jar-file /path/to/cookies.txt
```

When cookies are loaded, YaSINT prints whether any of them match the
Yandex domains queried by the tool.

## SOWEL classification

This tool uses the following OSINT techniques:

* [SOTL-1.4. Analyze Internal Identifiers](https://sowel.soxoj.com/internal-identifiers)
* [SOTL-2.2. Search For Accounts On Other Platforms](https://sowel.soxoj.com/other-platform-accounts)
* [SOTL-6.1. Check Logins Reuse To Find Another Account](https://sowel.soxoj.com/logins-reuse)
* [SOTL-6.2. Check Nicknames Reuse To Find Another Account](https://sowel.soxoj.com/nicknames-reuse)
