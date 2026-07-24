"""Load the full 7M-row dataset from the quarterly parquet parts in data/full/.

The combined file exceeds GitHub's 100 MB per-file limit, so it is stored as four
quarterly parts. Usage:

    from scripts.load_full_data import load_flights
    df = load_flights()
"""

from pathlib import Path

import pandas as pd

FULL = Path(__file__).resolve().parent.parent / "data" / "full"


def load_flights() -> pd.DataFrame:
    parts = sorted(FULL.glob("flights_part*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no parquet parts found in {FULL}")
    df = pd.concat((pd.read_parquet(p) for p in parts), ignore_index=True)
    return df.sort_values("FlightDate", ignore_index=True)


if __name__ == "__main__":
    df = load_flights()
    print(f"{len(df):,} rows | {df.FlightDate.min().date()} -> {df.FlightDate.max().date()}")
