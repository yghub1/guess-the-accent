"""Pull short reference recordings of real accented speakers.

Chatterbox copies the voice (and with it the accent) from a ~10 s sample.
Samples come from two open corpora, read straight from Hugging Face so only
the rows we need are downloaded:

  VCTK  (CC BY 4.0)    studio-quality read speech, CSTR Edinburgh
  EdAcc (CC BY-SA 4.0) conversational speech over Zoom, CSTR Edinburgh

Writes refs/<tag>-<n>.wav and refs/CREDITS.txt.
"""
import argparse
import io
import os
import sys
import time

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
from huggingface_hub import HfFileSystem

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "refs")
TARGET_SECONDS = 10.0
SR = 24000

# Accent tag -> VCTK speaker ids, from the corpus's speaker-info.txt.
VCTK = {
    "en-GB": ["p225", "p226"],   # Southern England F, Surrey M
    "en-IE": ["p295", "p245"],   # Dublin F, Dublin M
    "en-US": ["p333", "p345"],   # Indiana F, Florida M
    "en-CA": ["p303", "p316"],   # Toronto F, Alberta M
    "en-AU": ["p326", "p374"],   # Sydney M, M
    "en-NZ": ["p335"],           # F
    "en-IN": ["p248", "p251"],   # F, M
    "en-ZA": ["p314", "p347"],   # Cape Town F, Johannesburg M
}
# Accent tag -> EdAcc linguist label.
EDACC = {
    "en-NG": "Nigerian English",
    "en-KE": "Kenyan English",
    "en-GH": "Ghanain English",
    "en-EG": "Egyptian",
}

fs = HfFileSystem()


def resample(a, sr):
    if sr == SR:
        return a
    n = int(len(a) * SR / sr)
    return np.interp(np.linspace(0, len(a), n, endpoint=False), np.arange(len(a)), a).astype(np.float32)


def decode(cell):
    a, sr = sf.read(io.BytesIO(cell["bytes"]), dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    return resample(a, sr)


def stitch(clips):
    """Join clips with short gaps until ~TARGET_SECONDS, normalise loudness."""
    gap = np.zeros(int(0.25 * SR), dtype=np.float32)
    out, total = [], 0.0
    for c in clips:
        out += [c, gap]
        total += len(c) / SR
        if total >= TARGET_SECONDS:
            break
    a = np.concatenate(out[:-1])
    return a / (np.max(np.abs(a)) + 1e-9) * 0.9


def retry(fn, tries=6):
    """The Hub drops long range reads now and then; just ask again."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print("  retrying after:", str(e)[:80], file=sys.stderr)
            time.sleep(2 * (i + 1))


def read_group(f, g, cols):
    def go():
        with fs.open(f, block_size=8 * 2**20) as fh:
            return pq.ParquetFile(fh).read_row_group(g, columns=cols)
    return retry(go)


def rows_where(files, col, wanted, extra_cols):
    """Yield matching rows, downloading the audio column only for row groups that contain a match."""
    for f in files:
        md = retry(lambda: pq.ParquetFile(fs.open(f)).metadata)
        ci = md.schema.names.index(col)
        for g in range(md.num_row_groups):
            st = md.row_group(g).column(ci).statistics
            if st is not None and st.has_min_max and not any(st.min <= w <= st.max for w in wanted):
                continue
            keys = read_group(f, g, [col]).column(0).to_pylist()
            if not any(k in wanted for k in keys):
                continue
            print("  reading", os.path.basename(f), "group", g, file=sys.stderr, flush=True)
            for r in read_group(f, g, [col] + extra_cols).to_pylist():
                if r[col] in wanted:
                    yield r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated accent tags, e.g. en-EG")
    args = ap.parse_args()
    keep = set(args.only.split(",")) if args.only else None
    vctk = {t: v for t, v in VCTK.items() if keep is None or t in keep}
    edacc = {t: v for t, v in EDACC.items() if keep is None or t in keep}

    os.makedirs(OUT, exist_ok=True)
    credits = {}
    path = os.path.join(OUT, "CREDITS.txt")
    if os.path.exists(path):
        for line in open(path):
            if line.strip():
                credits[line.split()[0]] = line.rstrip("\n")

    # VCTK: read speech, take 3-7 s clips from the Sennheiser mic.
    want = {s: t for t, ss in vctk.items() for s in ss}
    got = {s: [] for s in want}
    files = sorted(retry(lambda: fs.glob("datasets/thelarryproject/vctk/train/*.parquet")))
    for r in rows_where(files if want else [], "speaker_id", set(want), ["mic_id", "duration_s", "ctc_mismatch", "audio"]):
        s = r["speaker_id"]
        if r["mic_id"] == "mic2" and 3 <= r["duration_s"] <= 7 and len(got[s]) < 4:
            got[s].append(decode(r["audio"]))
        if all(len(v) >= 4 for v in got.values()):
            break
    for t, ss in vctk.items():
        for i, s in enumerate(ss, 1):
            if not got[s]:
                print("no clips for", s, file=sys.stderr)
                continue
            sf.write(os.path.join(OUT, f"{t}-{i}.wav"), stitch(got[s]), SR)
            credits[f"{t}-{i}.wav"] = (f"{t}-{i}.wav  VCTK speaker {s}  CC BY 4.0  CSTR, University of Edinburgh")
            print("wrote", t, i, s)

    # EdAcc: conversational, so prefer longer clean turns and up to two speakers per accent.
    want = set(edacc.values())
    by_speaker = {}
    files = sorted(retry(lambda: fs.glob("datasets/edinburghcstr/edacc/data/*.parquet")))
    for r in rows_where(files if want else [], "accent", want, ["speaker", "text", "audio"]):
        words = len(r["text"].split())
        if words < 8 or any(x in r["text"] for x in ("<", "[", "(")):
            continue
        clips = by_speaker.setdefault((r["accent"], r["speaker"]), [])
        if len(clips) < 4:
            a = decode(r["audio"])
            if 3 <= len(a) / SR <= 9:
                clips.append(a)
    for t, label in edacc.items():
        speakers = sorted(
            [(k[1], v) for k, v in by_speaker.items() if k[0] == label and len(v) >= 2],
            key=lambda kv: -len(kv[1]),
        )[:2]
        for i, (spk, clips) in enumerate(speakers, 1):
            sf.write(os.path.join(OUT, f"{t}-{i}.wav"), stitch(clips), SR)
            credits[f"{t}-{i}.wav"] = (f"{t}-{i}.wav  EdAcc speaker {spk}  CC BY-SA 4.0  CSTR, University of Edinburgh")
            print("wrote", t, i, spk)

    with open(path, "w") as fh:
        fh.write("\n".join(credits[k] for k in sorted(credits)) + "\n")


if __name__ == "__main__":
    main()
