from setuptools import setup, find_packages

exec(open('yaseeker/_version.py').read())

with open('requirements.txt') as rf:
    requires = rf.read().splitlines()

with open('README.md') as fh:
    long_description = fh.read()

setup(
    name="yaseeker",
    version=__version__,
    description="Yandex profile OSINT tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/TAbdiukov/YaSeekerUltra",
    author="Tim Abdiukov",
    entry_points={'console_scripts': ['yaseeker = yaseeker.cli:run']},
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    install_requires=requires,
)
