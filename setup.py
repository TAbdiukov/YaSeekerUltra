from setuptools import setup, find_packages

exec(open('yasint/_version.py').read())

with open('requirements.txt') as rf:
    requires = rf.read().splitlines()

with open('README.md') as fh:
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
)
