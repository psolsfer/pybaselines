#!/usr/bin/env python
"""The setup script."""

from setuptools import setup, find_packages


with open('README.rst') as readme_file:
    long_description = readme_file.read()

requirements = [
    'numpy>=1.8',
    'scipy'
]

setup_requirements = [
]

test_requirements = [
    #'pytest>=3',
]

setup(
    author='Donald Erb',
    author_email='donnie.erb@gmail.com',
    python_requires='>=3.6',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Scientific/Engineering :: Chemistry',
        'Topic :: Scientific/Engineering :: Information Analysis',
        'Topic :: Scientific/Engineering :: Physics',
    ],
    description='A collection of baseline algorithms for fitting experimental data.',
    install_requires=requirements,
    license='BSD 3-clause',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    include_package_data=True,
    keywords=['materials characterization', 'materials science', 'materials engineering'],
    name='pybaselines',
    packages=find_packages(include=['pybaselines', 'pybaselines.*']),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/derb12/pybaselines',
    version='0.1.0',
    zip_safe=False,
)
