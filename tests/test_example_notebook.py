"""The example notebook runs top to bottom and prints the table and summary.

Slow: it loads a real weekend through FastF1 (on-disk cache, or the live
timing API when cold).
"""

from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "end_to_end_real_race.ipynb"


def test_example_notebook_runs_top_to_bottom_and_prints_the_report():
    notebook = nbformat.read(NOTEBOOK, as_version=4)

    NotebookClient(
        notebook, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}
    ).execute()

    printed = "".join(
        output.get("text", "")
        for cell in notebook.cells
        if cell.cell_type == "code"
        for output in cell.get("outputs", [])
    )
    assert "Candidate Strategy" in printed
    assert "Top-1 Strategy Match" in printed
    assert "Stop Window hits" in printed
