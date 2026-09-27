#!/usr/bin/env python3
r"""
mapper_utilization.py
Outputs: Location <TAB> Bin_Utilization_Pct
"""
import sys

for line in sys.stdin:
    fields = line.strip().split(",")
    if len(fields) < 10 or fields[0] == "Bin_ID":
        continue
    location = fields[2]
    utilization = fields[9]
    print("%s\t%s" % (location, utilization))
