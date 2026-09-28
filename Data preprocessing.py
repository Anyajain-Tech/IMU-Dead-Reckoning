"""
Data preprocessing: merge phone (S-) and vehicle (V-) trip files.

Steps per trip:
1. Read CSVs (UTF-8 first, Latin-1 fallback, since Latin-1 never fails and can silently corrupt text).
2. Unwrap midnight rollover in "seconds since midnight" timestamps.
3. Align streams using the first-row timestamps, then refine the offset by
   cross-correlating phone gyro magnitude with |vehicle yaw rate|
   (rotation-rate magnitude is independent of phone mount orientation).
4. Bin to a 10 Hz tick grid, averaging samples that share a tick.
5. Flag possible clock drift (lag at trip start vs end).

Outputs: merged_raw.csv and sync_verification_report.csv (per-trip PASS/WARN/FAIL).
"""
import sys, os, re
from pathlib import Path
import numpy as np
import pandas as pd

IN_COLAB = "google.colab" in sys.modules
if IN_COLAB:
    from google.colab import drive
    drive.mount("/content/drive")

SYNC_DIR = Path(os.environ.get("IDR_SYNC_DIR", "/content/drive/"))  ## Add the path of your dataser 
OUT_DIR  = Path(os.environ.get("IDR_MERGE_OUT", "/content/drive/")) ## Add the output path 
OUT_DIR.mkdir(parents=True, exist_ok=True)

ASSUMED_FS = 10.0                 # Hz -- the tick grid this pipeline is built around
MAX_SYNC_SEARCH_S = 2.0           # how far to search for a sync-lag correction
MIN_CORR_TO_TRUST = 0.35          # below this, there's not enough turning motion to judge sync at all
MIN_CORR_GAIN_TO_APPLY = 0.05     # require a real improvement before shifting away from the naive alignment
SAMPLE_RATE_WARN_PCT = 5.0        # warn if achieved rate differs from ASSUMED_FS by more than this
MAX_DROP_FRAC_WARN = 0.10         # warn if more than 10% of either file's rows didn't make it into the merge

# ---------------- file pairing ----------------
files = os.listdir(SYNC_DIR)
s_lookup = {re.sub(r"^S-", "", f).replace(".csv", "").lower(): f for f in files if f.startswith("S-")}
v_lookup = {re.sub(r"^V-", "", f).replace(".csv", "").lower(): f for f in files if f.startswith("V-")}
common_keys = sorted(set(s_lookup) & set(v_lookup))
trip_pairs = [(s_lookup[k], v_lookup[k]) for k in common_keys]
print(f"Valid pairs: {len(trip_pairs)}  (S-only: {len(set(s_lookup)-set(v_lookup))}, V-only: {len(set(v_lookup)-set(s_lookup))})")

# ---------------- encoding-safe reader ----------------
def read_csv_any_encoding(path):
    """Try UTF-8 first: it raises cleanly on real Latin-1 bytes. Latin-1 never
    raises, so trying it first would silently corrupt a UTF-8 file instead of
    failing -- verified this produces 'm/sÂ²' from a real 'm/s²' with no error."""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc), enc
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding="latin-1"), "latin-1 (fallback)"

def clean_columns(df):
    df.columns = [re.sub(r"\s+", " ", c.strip()) for c in df.columns]
    return df

class ColumnNotFound(Exception): pass

def find_col(df, label, contains=None, startswith=None):
    if startswith:
        matches = [c for c in df.columns if c.lower().startswith(startswith.lower())]
    else:
        matches = [c for c in df.columns if contains.lower() in c.lower()]
    if len(matches) != 1:
        raise ColumnNotFound(f"{label}: expected 1 match for '{contains or startswith}', got {matches}. "
                              f"Available columns: {list(df.columns)}")
    return matches[0]

def unwrap_midnight(seconds):
    """'seconds since midnight' wraps to 0 at midnight. Detect large negative
    jumps (a real time-travel jump would be < a fraction of a second; a
    midnight wrap is close to -86400) and add 86400 to everything after."""
    s = np.asarray(seconds, dtype=float).copy()
    d = np.diff(s)
    wraps = np.flatnonzero(d < -43200)
    for i in wraps:
        s[i + 1:] += 86400.0
    return s, len(wraps)

def best_extra_lag(a, b, fs, max_lag_s):
    """Cross-correlate two already-roughly-aligned equal-length series and
    return (extra_lag_seconds, corr_at_zero, corr_at_best)."""
    max_lag = int(round(max_lag_s * fs))
    n = min(len(a), len(b))
    a = a[:n]; b = b[:n]
    az = (a - np.nanmean(a)) / (np.nanstd(a) + 1e-9)
    bz = (b - np.nanmean(b)) / (np.nanstd(b) + 1e-9)
    def corr_at(lag):
        if lag < 0: aa, bb = az[-lag:], bz[:n + lag]
        elif lag > 0: aa, bb = az[:n - lag], bz[lag:]
        else: aa, bb = az, bz
        m = min(len(aa), len(bb))
        if m < fs * 5: return np.nan
        with np.errstate(invalid="ignore"):
            c = np.corrcoef(aa[:m], bb[:m])[0, 1]
        return c
    corr0 = corr_at(0)
    best_lag, best_c = 0, corr0 if np.isfinite(corr0) else -2.0
    for lag in range(-max_lag, max_lag + 1):
        c = corr_at(lag)
        if np.isfinite(c) and c > best_c:
            best_lag, best_c = lag, c
    return best_lag / fs, corr0, best_c

# ---------------- merge one trip ----------------
def merge_trip(s_filename, v_filename):
    s_df, s_enc = read_csv_any_encoding(SYNC_DIR / s_filename); s_df = clean_columns(s_df)
    v_df, v_enc = read_csv_any_encoding(SYNC_DIR / v_filename); v_df = clean_columns(v_df)

    dc          = find_col(s_df, "S DATE", startswith="DATE")
    v_time_col  = find_col(v_df, "V time-of-day", contains="Time Since Start of Day")
    acc_cols    = [find_col(s_df, f"S acc {a}", contains=f"ACCELEROMETER {a}") for a in "XYZ"]
    gyro_cols   = [find_col(s_df, f"S gyro {a}", contains=f"GYROSCOPE {a}") for a in "XYZ"]
    veh_speed   = find_col(v_df, "V speed", startswith="Velocity")
    veh_lat     = find_col(v_df, "V lat", startswith="Latitude")
    veh_lon     = find_col(v_df, "V lon", startswith="Longitude")
    veh_yawrate = find_col(v_df, "V yaw", contains="Yaw Rate")
    gps_sat     = find_col(v_df, "V sats", contains="No of GPS Satellites")

    s_df = s_df.reset_index(drop=True); v_df = v_df.reset_index(drop=True)

    ts = pd.to_datetime(s_df[dc], format="%Y-%m-%d %H:%M:%S:%f")
    s_abs_raw = (ts.dt.hour * 3600 + ts.dt.minute * 60 + ts.dt.second + ts.dt.microsecond / 1e6).values
    s_abs, s_wraps = unwrap_midnight(s_abs_raw)
    s_monotonic_violations = int((np.diff(s_abs) < 0).sum())

    v_abs_raw = pd.to_numeric(v_df[v_time_col], errors="coerce").values.astype(float)
    v_abs, v_wraps = unwrap_midnight(v_abs_raw)

    naive_shift = s_abs[0] - v_abs[0]
    v_abs_shifted = v_abs + naive_shift

    achieved_fs_s = 1.0 / np.median(np.diff(s_abs)) if len(s_abs) > 1 else np.nan
    fs_dev_pct = abs(achieved_fs_s - ASSUMED_FS) / ASSUMED_FS * 100 if np.isfinite(achieved_fs_s) else np.nan

    def bin_and_dedupe(df, t_seconds, cols):
        tmp = df[cols].copy()
        tmp["tick"] = np.round(t_seconds * ASSUMED_FS).astype(np.int64)
        n_before = len(tmp)
        agg = tmp.groupby("tick", as_index=False)[cols].mean()
        dup_frac = 1 - len(agg) / n_before if n_before else 0.0
        return agg, dup_frac

    s_agg, s_dup_frac = bin_and_dedupe(s_df, s_abs, acc_cols + gyro_cols)
    v_agg, v_dup_frac = bin_and_dedupe(v_df, v_abs_shifted, [veh_speed, veh_lat, veh_lon, veh_yawrate, gps_sat])

    merged0 = s_agg.merge(v_agg, on="tick", how="inner").sort_values("tick").reset_index(drop=True)

    # --- sync verification: rotation-rate magnitude is invariant to the (unknown) mount orientation ---
    extra_lag_s, corr0, corr_best = (np.nan, np.nan, np.nan)
    applied_extra_lag_s = 0.0
    sync_flag = "UNVERIFIED"
    drift_note = ""
    if len(merged0) > ASSUMED_FS * 10:
        gyro_mag = np.sqrt(sum(merged0[c].values ** 2 for c in gyro_cols))
        gyro_mag = gyro_mag - np.median(gyro_mag)
        veh_yaw_mag = np.abs(merged0[veh_yawrate].values)
        extra_lag_s, corr0, corr_best = best_extra_lag(gyro_mag, veh_yaw_mag, ASSUMED_FS, MAX_SYNC_SEARCH_S)
        if corr_best < MIN_CORR_TO_TRUST:
            sync_flag = "LOW_SIGNAL (too little turning to verify sync)"
        elif corr_best > corr0 + MIN_CORR_GAIN_TO_APPLY and abs(extra_lag_s) > 1.0 / ASSUMED_FS:
            applied_extra_lag_s = extra_lag_s
            sync_flag = f"REFINED (+{extra_lag_s:+.2f}s, corr {corr0:.2f}->{corr_best:.2f})"
        else:
            sync_flag = f"OK (corr {corr0:.2f})"

        # A single constant shift can only fix a fixed offset, not a clock RATE
        # difference (one device's clock running fractionally fast/slow). Check
        # this by finding the best lag independently in the first third and the
        # last third of the trip -- if a real turn-timing lag opens up between
        # the start and the end, the two clocks are drifting apart, and no
        # constant shift can fix the whole trip.
        third = len(merged0) // 3
        if third > ASSUMED_FS * 8 and corr_best >= MIN_CORR_TO_TRUST:
            lag_start, c0s, cbs = best_extra_lag(gyro_mag[:third], veh_yaw_mag[:third], ASSUMED_FS, MAX_SYNC_SEARCH_S)
            lag_end, c0e, cbe = best_extra_lag(gyro_mag[-third:], veh_yaw_mag[-third:], ASSUMED_FS, MAX_SYNC_SEARCH_S)
            if cbs >= MIN_CORR_TO_TRUST and cbe >= MIN_CORR_TO_TRUST and abs(lag_end - lag_start) > 2.0 / ASSUMED_FS:
                drift_note = f"POSSIBLE CLOCK DRIFT: lag at trip start {lag_start:+.2f}s vs trip end {lag_end:+.2f}s (a constant shift can't fix this)"

    if applied_extra_lag_s != 0.0:
        v_agg2, v_dup_frac = bin_and_dedupe(v_df, v_abs_shifted + applied_extra_lag_s, [veh_speed, veh_lat, veh_lon, veh_yawrate, gps_sat])
        merged = s_agg.merge(v_agg2, on="tick", how="inner").sort_values("tick").reset_index(drop=True)
    else:
        merged = merged0

    merged.columns = ["tick", "acc_x_raw", "acc_y_raw", "acc_z_raw", "gyro_x_raw", "gyro_y_raw", "gyro_z_raw",
                       "veh_Velocity", "veh_Latitude", "veh_Longitude", "veh_YawRate", "veh_GPS_Satellites"]
    merged["t_rel_phone"] = (merged["tick"] - merged["tick"].iloc[0]) / ASSUMED_FS
    merged["trip_id"] = s_filename
    merged["shift_applied_s"] = naive_shift + applied_extra_lag_s

    n_nan = int(merged[["acc_x_raw", "acc_y_raw", "acc_z_raw", "gyro_x_raw", "gyro_y_raw", "gyro_z_raw",
                         "veh_Velocity", "veh_Latitude", "veh_Longitude"]].isna().sum().sum())

    stats = dict(trip=s_filename, s_encoding=s_enc, v_encoding=v_enc,
                 s_rows=len(s_df), v_rows=len(v_df), merged_rows=len(merged),
                 s_midnight_wraps=s_wraps, v_midnight_wraps=v_wraps, s_time_monotonic_violations=s_monotonic_violations,
                 achieved_fs_hz=round(achieved_fs_s, 3) if np.isfinite(achieved_fs_s) else np.nan,
                 fs_deviation_pct=round(fs_dev_pct, 2) if np.isfinite(fs_dev_pct) else np.nan,
                 s_duplicate_tick_frac=round(s_dup_frac, 4), v_duplicate_tick_frac=round(v_dup_frac, 4),
                 drop_frac_s=round(1 - len(merged) / len(s_df), 4), drop_frac_v=round(1 - len(merged) / len(v_df), 4),
                 naive_shift_s=round(naive_shift, 3), sync_corr_at_naive=round(corr0, 3) if np.isfinite(corr0) else np.nan,
                 sync_corr_best=round(corr_best, 3) if np.isfinite(corr_best) else np.nan,
                 sync_extra_lag_applied_s=round(applied_extra_lag_s, 3), sync_flag=sync_flag, drift_note=drift_note, nan_count=n_nan)

    flags = []
    if s_monotonic_violations: flags.append(f"S timestamps non-monotonic ({s_monotonic_violations} violations)")
    if np.isfinite(fs_dev_pct) and fs_dev_pct > SAMPLE_RATE_WARN_PCT: flags.append(f"sample rate off by {fs_dev_pct:.1f}%")
    if stats["drop_frac_s"] > MAX_DROP_FRAC_WARN or stats["drop_frac_v"] > MAX_DROP_FRAC_WARN:
        flags.append(f"high drop fraction (S={stats['drop_frac_s']*100:.1f}%, V={stats['drop_frac_v']*100:.1f}%)")
    if "LOW_SIGNAL" in sync_flag or "REFINED" in sync_flag: flags.append(sync_flag)
    if drift_note: flags.append(drift_note)
    if n_nan: flags.append(f"{n_nan} NaNs in core columns")
    stats["overall"] = "PASS" if not flags else ("WARN: " + "; ".join(flags))

    keep = ["tick", "t_rel_phone", "shift_applied_s", "acc_x_raw", "acc_y_raw", "acc_z_raw",
            "gyro_x_raw", "gyro_y_raw", "gyro_z_raw", "veh_Velocity", "veh_Latitude", "veh_Longitude",
            "veh_YawRate", "veh_GPS_Satellites", "trip_id"]
    return merged[keep], stats

# ---------------- process all trips ----------------
all_trips, report = [], []
for s_file, v_file in trip_pairs:
    print(f"Processing: {s_file}")
    try:
        df, stats = merge_trip(s_file, v_file)
    except ColumnNotFound as e:
        print(f"  SKIPPED (column problem): {e}")
        report.append(dict(trip=s_file, overall=f"FAIL: {e}"))
        continue
    except Exception as e:
        print(f"  SKIPPED (unexpected error): {e}")
        report.append(dict(trip=s_file, overall=f"FAIL: {type(e).__name__}: {e}"))
        continue
    all_trips.append(df)
    report.append(stats)
    print(f"  {stats['merged_rows']}/{stats['s_rows']} rows | fs={stats['achieved_fs_hz']}Hz | "
          f"sync: {stats['sync_flag']} | {stats['overall']}")

full_df = pd.concat(all_trips, ignore_index=True) if all_trips else pd.DataFrame()
report_df = pd.DataFrame(report)

full_df.to_csv(OUT_DIR / "merged_raw.csv", index=False, encoding="utf-8")
report_df.to_csv(OUT_DIR / "sync_verification_report.csv", index=False, encoding="utf-8")

print(f"\nSaved merged_raw.csv ({len(full_df)} rows, UTF-8) and sync_verification_report.csv to {OUT_DIR}")
n_fail = report_df["overall"].str.startswith("FAIL").sum() if len(report_df) else 0
n_warn = report_df["overall"].str.startswith("WARN").sum() if len(report_df) else 0
print(f"\nSUMMARY: {len(report_df) - n_fail - n_warn} PASS, {n_warn} WARN, {n_fail} FAIL out of {len(report_df)} trips")
if n_warn or n_fail:
    print("\nTrips needing a look:")
    print(report_df[report_df["overall"] != "PASS"][["trip", "overall"]].to_string(index=False))