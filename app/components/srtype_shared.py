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

# Full department/bureau names for category pill abbreviations. Baltimore's 311
# system doesn't publish a prefix glossary, so these are inferred from the content
# of each prefix's subcategories (e.g. "WW-Hydrant Leaking", "WW-Sediment or Erosion
# Problem" → Water & Wastewater). Extend as new prefixes appear.
CATEGORY_NAMES: dict[str, str] = {
    "BCLB":    "Board of Liquor License Commissioners",
    "BGE":     "Baltimore Gas & Electric (utility coordination)",
    "BPD":     "Police Department",
    "CC":      "City Council",
    "DPW":     "Public Works",
    "ECC":     "Emergency Communications",
    "EOC":     "Emergency Operations Center",
    "FCCS":    "Finance — Customer & Collections Services",
    "FCDA":    "Finance — Central Debt & Accounts",
    "FCPF":    "Finance — Citations & Parking Fines",
    "FIN":     "Finance",
    "FINBAPS": "Finance — Accounting & Payroll Services",
    "FIR":     "Fire Department",
    "FOR":     "Forestry",
    "HCD":     "Housing & Community Development",
    "HLTH":    "Health Department",
    "MOHS":    "Mayor's Office of Homeless Services",
    "MOIT":    "Mayor's Office of Information Technology",
    "OEM":     "Office of Emergency Management",
    "PABC":    "Parking Authority of Baltimore City",
    "RP":      "Recreation & Parks",
    "SW":      "Solid Waste",
    "TEC":     "Transportation — Engineering & Construction",
    "TR":      "Transportation — Right-of-Way",
    "TRA":     "Transportation — Automated Traffic Enforcement",
    "TRC":     "Transportation — Conduits",
    "TRD":     "Transportation — Administration",
    "TRM":     "Transportation — Maintenance",
    "TRS":     "Transportation — Parking Enforcement",
    "TRT":     "Transportation — Traffic",
    "TTR":     "Transportation — Towing & Vehicle Recovery",
    "WW":      "Water & Wastewater",
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


def category_selector(ranked: list[str], top_n: int, key: str) -> str | None:
    """Two-tier category picker shared by the Service Category Explorer and its
    equity-flavored sibling.

    The `top_n` highest-ranked categories (sorted alphabetically, so they read as a
    scannable grid rather than a ranking) sit in an always-visible row sized to fit
    on one line on mobile, labeled by their acronym with a small legend underneath —
    these are the categories a returning user will recognize and want to jump to
    quickly. Lower-ranked categories are tucked behind an expander and labeled by
    their full department name instead — a user opening that drawer is browsing,
    not recalling an acronym, so the name carries more information than the code
    and no separate legend is needed. Selecting in one tier clears the other so
    there's always at most one active category. `ranked` should already be ordered
    by whatever the caller wants "top" to mean (e.g. current-year volume).
    """
    top_cats = sorted(ranked[:top_n])
    rest_cats = sorted(ranked[top_n:])
    top_key, more_key = f"{key}_top", f"{key}_more"

    top_sel = st.pills(
        "Category", top_cats, key=top_key,
        on_change=lambda: st.session_state.update({more_key: None}),
    )
    top_known = {c: CATEGORY_NAMES[c] for c in top_cats if c in CATEGORY_NAMES}
    if top_known:
        st.caption("  ·  ".join(f"**{k}** {v}" for k, v in sorted(top_known.items())))

    more_sel = None
    if rest_cats:
        with st.expander(f"+ {len(rest_cats)} lower-ranked categories"):
            more_sel = st.pills(
                "More categories", rest_cats,
                format_func=lambda c: CATEGORY_NAMES.get(c, c),
                key=more_key,
                on_change=lambda: st.session_state.update({top_key: None}),
            )

    return top_sel or more_sel


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


@st.cache_data
def load_geo_srtype_history(data_dir: Path, geo_key: str) -> pd.DataFrame:
    """All available geo×SRType metrics years for one geo level, combined with a `year` column."""
    dfs = []
    for p in sorted(data_dir.glob(f"{geo_key}_srtype_metrics_*.parquet")):
        try:
            y = int(p.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_parquet(p)
        df["year"] = y
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
