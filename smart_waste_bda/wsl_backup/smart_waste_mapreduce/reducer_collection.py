#!/usr/bin/env python3
r"""
reducer_collection.py
Counts, for each location, how many records were Collected vs Pending,
and works out the collection rate as a percentage.
Output columns: Location <TAB> Collected <TAB> Pending <TAB> Collection_Rate_Pct
"""
import sys

current_location = None
collected = 0
pending = 0


def emit(location, collected, pending):
    total = collected + pending
    rate = (collected / total * 100) if total else 0.0
    print("%s\t%d\t%d\t%.2f" % (location, collected, pending, rate))


for line in sys.stdin:
    location, status = line.strip().split("\t")

    if current_location == location:
        pass
    else:
        if current_location is not None:
            emit(current_location, collected, pending)
        current_location = location
        collected = 0
        pending = 0

    if status == "Collected":
        collected += 1
    else:
        pending += 1

if current_location is not None:
    emit(current_location, collected, pending)
