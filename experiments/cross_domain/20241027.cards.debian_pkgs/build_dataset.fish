#!/usr/bin/env fish

# CARDS: A collection of package, revision, and miscelleneous dependency graphs
# Dataset URL: https://doi.org/10.5281/zenodo.14245890
# Author: Euxane TRAN-GIRARD (https://orcid.org/0009-0003-4190-7151)
# Licenses: EUPL-1.2 (script), ODbL-1.0 (dataset)

set today (date "+%Y%m%d" -d "$argv[1]")
set prefix $today.debian_pkgs

set mirror "http://ftp.debian.org"
set dist debian/dists/stable/main/binary-amd64

set list $prefix.packages.txt.gz
test -f $list ||
    curl $mirror/$dist/Packages.gz >$list

set deps $prefix.deps.gz
test -f $deps ||
    zcat $list |
        ./extract_deb_dependencies.py |
        gzip >$deps

set tdag $prefix.tdag.gz
test -f $tdag ||
    zcat $deps |
        toposort --break-cycles |
        gzip >$tdag
