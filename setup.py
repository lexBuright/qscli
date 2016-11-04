#!/usr/bin/python

from setuptools import setup

DESCRIPTION = 'qscli is a suite of command line tools for quantified-self types of activity'

TEST_REQUIRES = ['zodb'] # for zodb backend
setup(
    name='qscli',
    version='0.1',
    description=DESCRIPTION,
    long_description=DESCRIPTION,
    author='Lex Buright',
    author_email='lex.buright@gmail.com',
    url='git@github.com:lexBuright/qscli.git',
    packages=[
        'qscli',
    ],
    install_requires=[],
    test_requires=TEST_REQUIRES,
    extras_require={'test': TEST_REQUIRES},
    license="GPLv3",
    tests=['tests'],
    test_suite='nose.collector',
    keywords='quantified self tracking statistics',
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GPLv3 License',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
    ],
)
