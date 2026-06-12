from setuptools import setup, find_packages

exec(open('yasint/_version.py', encoding='utf-8').read())

with open('requirements.txt', encoding='utf-8') as rf:
    requires = [
        line.strip()
        for line in rf
        if line.strip() and not line.lstrip().startswith('#')
    ]

with open('README.md', encoding='utf-8') as fh:
    long_description = fh.read()

setup(
    name="yasint",
    version=__version__,
    description="Yandex profile OSINT tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/TAbdiukov/YaSINT",
    author="Tim Abdiukov",
    entry_points={'console_scripts': ['yasint = yasint.cli:run']},
    packages=find_packages(),
    include_package_data=True,
    install_requires=requires,
    python_requires=">=3.8",
    license_files=["NOTICE", "LICENCES/MIT-Soxoj.txt"],
    project_urls={
        "Source": "https://github.com/TAbdiukov/YaSINT",
        "Issues": "https://github.com/TAbdiukov/YaSINT/issues",
        "Changelog": "https://github.com/TAbdiukov/YaSINT/blob/main/CHANGELOG.md",
    },
    classifiers=[
        "Environment :: Console",
        'Intended Audience :: Information Technology',
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Security",
    ],
)
