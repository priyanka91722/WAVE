#!/usr/bin/env python3
r"""
mapper_date.py
Outputs: Date <TAB> Waste_Generated
"""
import sys

for line in sys.stdin:
    fields = line.strip().split(",")
    if len(fields) < 10 or fields[0] == "Bin_ID":
        continue
    date = fields[1]
    waste = fields[4]
    print("%s\t%s" % (date, waste))
