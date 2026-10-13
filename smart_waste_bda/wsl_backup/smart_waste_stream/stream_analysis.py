#!/usr/bin/env python3
r"""
stream_analysis.py
Simulates a simple stream of bin events (one event = one row from the
cleaned dataset, in date order) and demonstrates two streaming-data
techniques on it:

1. Bloom Filter -- has this Bin_ID been seen before in the stream?
   Useful for spotting a bin reporting for the very first time, without
   storing every Bin_ID ever seen (a real sensor network could have
   millions of bins; a Bloom Filter uses a small, fixed amount of memory).

2. DGIM -- estimate how many overflow events happened in the last N
   events, without storing the last N events themselves. DGIM keeps
   only a handful of "buckets" no matter how big N is.

This is a SIMULATION: we read already-cleaned data and feed it through
the stream one row at a time. No Kafka, no real sensors, no Spark
Streaming -- exactly as planned.

Run:
    python3 stream_analysis.py
"""

import csv
import hashlib


# =====================================================================
# 1. BLOOM FILTER
# =====================================================================
class BloomFilter:
    """
    A Bloom Filter answers "have I seen this item before?" using a fixed
    array of bits, no matter how many items come in.

    - add(item): mark this item as seen (flips a few bits to 1)
    - might_contain(item): True if the item MIGHT have been seen before

    It can occasionally say "yes" for an item that was never actually
    added (a false positive) -- that is the trade-off for using so
    little memory. It NEVER says "no" for something that really was
    added (no false negatives).
    """

    def __init__(self, size=2000, num_hashes=3):
        self.size = size
        self.num_hashes = num_hashes
        self.bits = [0] * size

    def _hash_positions(self, item):
        positions = []
        for i in range(self.num_hashes):
            digest = hashlib.md5(f"{item}-{i}".encode()).hexdigest()
            positions.append(int(digest, 16) % self.size)
        return positions

    def add(self, item):
        for pos in self._hash_positions(item):
            self.bits[pos] = 1

    def might_contain(self, item):
        return all(self.bits[pos] for pos in self._hash_positions(item))


# =====================================================================
# 2. DGIM
# =====================================================================
class DGIM:
    """
    DGIM estimates how many 1s occurred in the last `window_size` bits
    of a stream, using only O(log(window_size)) memory -- it never
    stores the actual bits.

    It works by grouping 1s into "buckets" whose sizes are powers of 2
    (1, 2, 4, 8, ...). Whenever there would be 3 buckets of the same
    size, the two oldest are merged into one bucket of double size.
    The estimate is: (sum of all bucket sizes) - (half of the oldest
    bucket's size), because we're not sure how much of the oldest
    bucket still falls inside the window.
    """

    def __init__(self, window_size):
        self.window_size = window_size
        self.buckets = []   # list of [timestamp, size], oldest first
        self.current_time = 0

    def add(self, bit):
        self.current_time += 1

        # Drop buckets that have fully slid out of the window
        cutoff = self.current_time - self.window_size
        self.buckets = [b for b in self.buckets if b[0] > cutoff]

        if bit == 1:
            self.buckets.append([self.current_time, 1])
            self._merge()

    def _merge(self):
        # Oldest-first list. If 3 buckets of the same size appear, merge
        # the two OLDEST of the three into one double-size bucket, and
        # keep the third (newest) bucket untouched.
        i = 0
        while i <= len(self.buckets) - 3:
            if self.buckets[i][1] == self.buckets[i + 1][1] == self.buckets[i + 2][1]:
                merged = [self.buckets[i + 1][0], self.buckets[i][1] * 2]
                self.buckets = self.buckets[:i] + [merged] + self.buckets[i + 2:]
                i = 0   # a merge can trigger another merge further along; restart the scan
            else:
                i += 1

    def estimate_count(self):
        if not self.buckets:
            return 0
        total = sum(size for _, size in self.buckets)
        oldest_size = self.buckets[0][1]
        return total - oldest_size // 2


# =====================================================================
# 3. STREAM SIMULATION
# =====================================================================
INPUT_CSV = "/mnt/c/Users/Priyanka Chavan/Desktop/smart_waste_bda/data/cleaned/waste_cleaned_full.csv"
DGIM_WINDOW = 1000          # look at the "last 1000 events" for overflow estimation
SNAPSHOT_EVERY = 20000      # print a comparison every N events


def run_stream():
    bloom = BloomFilter(size=2000, num_hashes=3)
    dgim = DGIM(window_size=DGIM_WINDOW)

    seen_bins = set()          # ONLY used to measure the Bloom Filter's accuracy;
                                # a real system with millions of bins wouldn't keep this
    false_positives = 0
    new_bins_detected = 0
    recent_bits = []           # ONLY used to compute the exact count for comparison

    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for event_no, row in enumerate(reader, start=1):
            bin_id = row["Bin_ID"]
            is_overflow = 1 if row["Overflow_Status"] == "Yes" else 0

            # ---- Bloom Filter: is this a bin we've never seen before? ----
            already_flagged = bloom.might_contain(bin_id)
            if not already_flagged:
                new_bins_detected += 1
            elif bin_id not in seen_bins:
                # Bloom filter said "seen before" but it actually wasn't --
                # a false positive. Rare, and harmless here (see explanation).
                false_positives += 1
            bloom.add(bin_id)
            seen_bins.add(bin_id)

            # ---- DGIM: track overflow events in a rolling window ----
            dgim.add(is_overflow)
            recent_bits.append(is_overflow)
            if len(recent_bits) > DGIM_WINDOW:
                recent_bits.pop(0)

            if event_no % SNAPSHOT_EVERY == 0:
                exact = sum(recent_bits)
                estimate = dgim.estimate_count()
                error = abs(estimate - exact)
                print("Event %-6d | DGIM estimate: %-4d | Exact count: %-4d | Error: %d" %
                      (event_no, estimate, exact, error))

    return event_no, new_bins_detected, false_positives, bloom, dgim, recent_bits, seen_bins


def main():
    print("Starting simulated stream from: %s\n" % INPUT_CSV)
    print("===== DGIM: overflow events in the last %d events (checked periodically) =====" % DGIM_WINDOW)
    total_events, new_bins, false_positives, bloom, dgim, recent_bits, seen_bins = run_stream()

    print("\n===== FINAL DGIM ESTIMATE (last %d events of the stream) =====" % DGIM_WINDOW)
    exact_final = sum(recent_bits)
    estimate_final = dgim.estimate_count()
    print("DGIM estimate : %d overflow events" % estimate_final)
    print("Exact count   : %d overflow events" % exact_final)
    print("Error         : %d" % abs(estimate_final - exact_final))

    print("\n===== BLOOM FILTER SUMMARY =====")
    print("Total events processed         : %d" % total_events)
    print("Distinct bins actually seen    : %d" % len(seen_bins))
    print("New bins detected by the filter: %d" % new_bins)
    print("False positives during the run : %d" % false_positives)

    print("\n===== BLOOM FILTER SPOT-CHECK =====")
    test_known = "B01-ORG-01"
    test_fake = "B99-FAKE-99"
    print("Is '%s' recognized as seen? -> %s (it really was in the stream)" %
          (test_known, bloom.might_contain(test_known)))
    print("Is '%s' recognized as seen? -> %s (it was NEVER in the stream)" %
          (test_fake, bloom.might_contain(test_fake)))


if __name__ == "__main__":
    main()
