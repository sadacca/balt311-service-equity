"""Shared SRType category constants and loaders.

Used by the Operations tab and the Service Category Explorer (and, going forward,
the Service Category Equity Explorer and Equity Adjusted tabs) — promoted here so
the category-pill / performance-table scaffolding stays consistent across all of
them rather than drifting apart as separate copies.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

# Minimum requests in a geo×SRType cell to display (suppresses noise; adjustable without rerunning pipeline)
MIN_GEO_SRTYPE_N = 5

# Full department names for category pill abbreviations.
# Source: Baltimore City 311 system (balt311.baltimorecity.gov). Extend as new prefixes appear.
CATEGORY_NAMES: dict[str, str] = {
    "BGE":  "BGE Street Lights",
    "BCRP": "Recreation & Parks",
    "CDW":  "Construction & Development",
    "CHE":  "Environmental Services",
    "DPW":  "Public Works",
    "ECC":  "Emergency Communications",
    "FF":   "Fire & Flood",
    "GRM":  "Grounds Maintenance",
    "HCD":  "Housing & Community Development",
    "MONO": "Parking Authority",
    "PC":   "Police Commissioner",
    "SW":   "Solid Waste",
    "TRS":  "Transportation",
}

EXCLUDED_CATEGORIES = {"TEST"}


def extract_categories(sr: pd.DataFrame) -> list[str]:
    """Return sorted unique hyphen-prefixes from SRType names (e.g. 'SW', 'HCD', 'TRS')."""
    return sorted({
        name.split("-")[0].strip()
        for name in sr["SRType"]
        if isinstance(name, str) and "-" in name
        and name.split("-")[0].strip()
        and name.split("-")[0].strip() not in EXCLUDED_CATEGORIES
    })


def category_pills(categories: list[str], key: str) -> str | None:
    """Render the category pill row + department-name legend caption.

    Returns the selected prefix, or None when "All" (or nothing) is selected.
    """
    cat_sel = st.pills("Category", ["All"] + categories, default="All", key=key)
    selected = cat_sel if (cat_sel and cat_sel != "All") else None
    known = {c: CATEGORY_NAMES[c] for c in categories if c in CATEGORY_NAMES}
    if known:
        st.caption("  ·  ".join(f"**{k}** {v}" for k, v in sorted(known.items())))
    return selected


@st.cache_data
def load_srtype_history(data_dir: Path) -> pd.DataFrame:
    """All available srtype_metrics years combined into one DataFrame."""
    dfs = []
    for p in sorted(data_dir.glob("srtype_metrics_*.parquet")):
        try:
            y = int(p.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_parquet(p)
        df["year"] = y
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


@st.cache_data
def load_geo_srtype_metrics(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)
