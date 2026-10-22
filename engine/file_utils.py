"""Centralized file and data loading utilities for ForgeGuard Decision Engine.

Enables zero-hardcoding operation by providing dynamic ingestion of DataFrames,
JSON configurations, and dictionary mappings from arbitrary file paths or streams.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


def load_dataframe_or_path(data: pd.DataFrame | str | Path | Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Load a pandas DataFrame dynamically from an in-memory object or external file.

    Supported formats when passing a file path (str or Path):
    - CSV (.csv)
    - JSON (.json)
    - Parquet (.parquet, .pq)

    Args:
        data: A pandas DataFrame, a file path string or Path, or a sequence of row mappings.

    Returns:
        A loaded pandas DataFrame.

    Raises:
        FileNotFoundError: If a file path string or Path is provided but does not exist.
        TypeError: If data is not a DataFrame, valid file path, or sequence of mappings.
        ValueError: If the file format cannot be parsed or file is empty.
    """
    if isinstance(data, pd.DataFrame):
        return data

    if isinstance(data, Path):
        if not data.is_file():
            raise FileNotFoundError(f"Data file not found: {data}")
        path = data
    elif isinstance(data, str):
        path = Path(data)
        if path.is_file():
            pass
        elif any(data.lower().endswith(ext) for ext in (".csv", ".json", ".parquet", ".pq", ".tsv", ".txt")):
            raise FileNotFoundError(f"Data file not found: {data}")
        else:
            raise TypeError(f"Expected pandas DataFrame, file path (str or Path), or list of dicts, got str ({data!r}).")
    elif isinstance(data, (list, tuple)) and all(isinstance(x, Mapping) for x in data):
        return pd.DataFrame(data)
    else:
        raise TypeError(
            f"Expected pandas DataFrame, file path (str or Path), or list of dicts, got {type(data).__name__}."
        )

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    elif suffix == ".json":
        return pd.read_json(path)
    elif suffix in (".parquet", ".pq"):
        return pd.read_parquet(path)
    else:
        # Fallback: attempt CSV first, then JSON
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.read_json(path)




def load_json_or_dict(data: Mapping[str, Any] | Sequence[Any] | str | Path) -> dict[str, Any] | list[Any]:
    """Load a JSON structure dynamically from a file path or in-memory collection.

    Args:
        data: A dictionary/mapping, list, or file path (str or Path) to a JSON file.

    Returns:
        Loaded dictionary or list data structure.

    Raises:
        FileNotFoundError: If a file path is provided but does not exist.
        TypeError: If data is neither a collection nor a file path string/Path.
    """
    if isinstance(data, (str, Path)):
        path = Path(data)
        if not path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {data}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if isinstance(data, Mapping):
        return dict(data)

    if isinstance(data, (list, tuple)):
        return list(data)

    raise TypeError(
        f"Expected dict/mapping, list, or file path (str or Path), got {type(data).__name__}."
    )


def save_json(data: Any, filepath: str | Path, indent: int = 2) -> None:
    """Save serializable data to an external JSON file, creating parent directories if needed.

    Args:
        data: Serializable data structure (dict, list, primitive).
        filepath: Target file path (str or Path).
        indent: Indentation formatting level (default 2).
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)
