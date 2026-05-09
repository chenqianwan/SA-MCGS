#!/usr/bin/env python

# CARDS: A collection of package, revision, and miscelleneous dependency graphs
# Dataset URL: https://doi.org/10.5281/zenodo.14245890
# Author: Euxane TRAN-GIRARD (https://orcid.org/0009-0003-4190-7151)
# Licenses: EUPL-1.2 (script), ODbL-1.0 (dataset)

from dataclasses import dataclass
import sys
import re


@dataclass
class Package:
    name: str
    provides: list[str]
    depends: list[str]


def extract_dep_name(dep_spec):
    return dep_spec.split(' (')[0].split(':')[0].strip()


def extract_dep_list(dep_list):
    return [
        extract_dep_name(dep)
        for dep in re.split(r', | \| ', dep_list)  # taking all alternatives
    ]


def read_packages(pairs):
    name, provides, depends = '', [], []
    for line in pairs:
        line = line.strip()
        if line == '':
            yield Package(name, provides, depends)
            name, provides, depends = '', [], []
            continue

        key, val = line.split(': ', 1)
        match key.strip():
            case 'Package':
                name = val.strip()
            case 'Provides':
                provides = extract_dep_list(val)
            case 'Depends' | 'Pre-Depends':
                depends += extract_dep_list(val)


def read_line_pairs(input):
    current = None
    for line in input:
        if line.startswith(' '):  # multi-line field continuation
            current = (current or '') + line.rstrip()
        else:
            if current is not None:
                yield current
            current = line.rstrip()


def build_provider_map(pkgs):
    providers = {}
    for pkg in pkgs:
        for provided in pkg.provides:
            providers[provided] = providers.get(provided, []) + [pkg.name]
    return providers


def resolve(provider_map, deps):
    for dep in deps:
        yield from provider_map.get(dep, [dep])


pkgs = list(read_packages(read_line_pairs(sys.stdin)))
provider_map = build_provider_map(pkgs)
for pkg in pkgs:
    deps = list(resolve(provider_map, pkg.depends))
    print(' '.join([pkg.name] + deps))
