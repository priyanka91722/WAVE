#!/usr/bin/env python3
r"""
mapper_wastetype.py
Outputs: Waste_Type <TAB> Waste_Generated
"""
import sys

for line in sys.stdin:
    fields = line.strip().split(",")
    if len(fields) < 10 or fields[0] == "Bin_ID":
        continue
    waste_type = fields[3]
    waste = fields[4]
    print("%s\t%s" % (waste_type, waste))

