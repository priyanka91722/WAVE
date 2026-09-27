#!/usr/bin/env python3
r"""
mapper_location.py
Reads the waste CSV, line by line, and outputs:
    Location <TAB> Waste_Generated
Skips the header row wherever it appears in the file.
"""
import sys

for line in sys.stdin:
    fields = line.strip().split(",")
    if len(fields) < 10 or fields[0] == "Bin_ID":
        continue  # skip header or broken line
    location = fields[2]
    waste = fields[4]
    print("%s\t%s" % (location, waste))
