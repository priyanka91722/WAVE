#!/usr/bin/env python3
r"""
reducer_sum.py
A SHARED reducer used by several jobs (location, waste type, date, utilization).
Hadoop sends this program lines already SORTED by key.
So all lines for the same key arrive one after another (this is the
"shuffle and sort" step). We add up the value for each key and print
the total (and count, and average) when the key changes.

Output columns: key <TAB> total <TAB> count <TAB> average
"""
import sys

current_key = None
total = 0.0
count = 0


def emit(key, total, count):
    print("%s\t%.2f\t%d\t%.2f" % (key, total, count, total / count))


for line in sys.stdin:
    key, value = line.strip().split("\t")
    value = float(value)

    if current_key == key:
        total += value
        count += 1
    else:
        if current_key is not None:
            emit(current_key, total, count)
        current_key = key
        total = value
        count = 1

if current_key is not None:
    emit(current_key, total, count)
