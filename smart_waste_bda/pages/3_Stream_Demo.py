import os
import time
import hashlib
from collections import deque

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Stream Demo", layout="wide")
try:
    from style import inject_css
    inject_css()
except ImportError:
    pass

CSV_PATH = r"C:\Users\Priyanka Chavan\Desktop\smart_waste_bda\data\cleaned\waste_cleaned.csv"  # <-- CHANGE THIS
WINDOW = 100


class Bloom:
    def __init__(self, m, k=3):
        self.m, self.k = m, k
        self.bits = bytearray(m)

    def _idx(self, key):
        return [int(hashlib.md5(f"{i}|{key}".encode()).hexdigest(), 16) % self.m for i in range(self.k)]

    def add(self, key):
        for i in self._idx(key):
            self.bits[i] = 1

    def check(self, key):
        return all(self.bits[i] for i in self._idx(key))

    def fill(self):
        return sum(self.bits) / self.m


class DGIM:
    """Counts 1s in the last WINDOW bits using exponentially growing buckets."""
    def __init__(self, window):
        self.window, self.t = window, 0
        self.buckets = []  # [timestamp, size], newest first

    def add(self, bit):
        self.t += 1
        while self.buckets and self.buckets[-1][0] <= self.t - self.window:
            self.buckets.pop()
        if bit == 1:
            self.buckets.insert(0, [self.t, 1])
            size = 1
            while True:
                idx = [i for i, b in enumerate(self.buckets) if b[1] == size]
                if len(idx) > 2:
                    newer, older = idx[-2], idx[-1]
                    self.buckets[newer][1] = size * 2
                    self.buckets.pop(older)
                    size *= 2
                else:
                    break

    def estimate(self):
        if not self.buckets:
            return 0
        return sum(b[1] for b in self.buckets) - self.buckets[-1][1] // 2


if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found: {CSV_PATH}. Fix CSV_PATH at the top of this file.")
    st.stop()


@st.cache_data
def load(path):
    df = pd.read_csv(path)
    if "Date" in df.columns:
        df = df.sort_values("Date", kind="stable")
    bits = df["IsSpoiled"].astype(str).str.lower().isin(["true", "1", "yes"]).astype(int).tolist()
    keys = (df["ItemName"].astype(str) + "|" + df["StoreLocation"].astype(str)).tolist()
    return keys, bits


try:
    keys, bits = load(CSV_PATH)
except KeyError as e:
    st.error(f"Column not found in the CSV: {e}")
    st.stop()

st.markdown("<h1 style='text-align:center'>Stream Processing Demo</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;opacity:0.7'>The cleaned dataset is replayed one record at a time "
    "as if it were a live stream</p>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center'><b>Bloom Filter</b> remembers every item-store pair using very "
    "little memory and flags repeats. <b>DGIM</b> estimates how many of the last "
    f"{WINDOW} records were spoiled without storing the whole window.</p>",
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns(3)
with c1:
    bloom_bits = st.slider("Bloom filter size (bits)", 128, 4096, 2048, step=128)
with c2:
    n_records = st.slider("Records to stream", 100, len(keys), len(keys), step=50)
with c3:
    delay = st.slider("Replay speed (seconds per update)", 0.0, 0.3, 0.05, step=0.01)

if st.button("Replay stream"):
    bloom, dgim = Bloom(bloom_bits, 3), DGIM(WINDOW)
    recent = deque(maxlen=WINDOW)
    seen = set()
    new = dup = fp = 0
    est_hist, exact_hist = [], []
    box, chart, prog = st.empty(), st.empty(), st.progress(0)

    for i in range(n_records):
        key, bit = keys[i], bits[i]
        if bloom.check(key):
            dup += 1
            if key not in seen:
                fp += 1
        else:
            new += 1
            bloom.add(key)
        seen.add(key)

        dgim.add(bit)
        recent.append(bit)
        est_hist.append(dgim.estimate())
        exact_hist.append(sum(recent))

        if (i + 1) % 10 == 0 or i + 1 == n_records:
            with box.container():
                m = st.columns(6)
                m[0].metric("Records processed", i + 1)
                m[1].metric("New item-store pairs", new)
                m[2].metric("Flagged as already seen", dup)
                m[3].metric("Bloom false positives", fp)
                m[4].metric(f"Spoiled in last {WINDOW} (DGIM)", est_hist[-1])
                m[5].metric(f"Spoiled in last {WINDOW} (exact)", exact_hist[-1])
                st.caption(f"Bloom filter fill: {bloom.fill() * 100:.1f}% of {bloom_bits} bits set")
            chart.line_chart(pd.DataFrame({"DGIM estimate": est_hist, "Exact count": exact_hist}))
            prog.progress((i + 1) / n_records)
            time.sleep(delay)

    st.success(f"Stream finished: {n_records} records processed.")
    st.caption("A Bloom filter never misses a repeat but can wrongly flag a new pair (a false positive). "
               "Shrink the filter size and replay again to watch false positives rise. DGIM's estimate "
               "stays within 50% of the exact count by design.")
else:
    st.info("Set the options above and press **Replay stream**.")