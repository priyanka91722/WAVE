#!/usr/bin/env python3
r"""
mapper_collection.py
Outputs: Location <TAB> Collection_Status
(one line per bin-day record; the reducer will count Collected vs Pending)
"""
import sys

for line in sys.stdin:
    fields = line.strip().split(",")
    if len(fields) < 10 or fields[0] == "Bin_ID":
        continue
    location = fields[2]
    status = fields[6]
    print("%s\t%s" % (location, status))
