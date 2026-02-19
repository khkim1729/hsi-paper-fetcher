# hsi-paper-fetcher

A collection of crawling tools for downloading Hyperspectral Imaging (HSI) research papers and related data.

> **[한국어 문서 (Korean)](README_ko.md)**

---

## Project Structure

```
hsi-paper-fetcher/
├── crawling_ieee_2023_2025.py    # IEEE TGRS bulk PDF downloader (Linux & Windows)
├── Crawling_IEEE_year.ipynb      # IEEE year-based crawling (notebook)
├── Crawling_ScienceDirect.ipynb  # ScienceDirect crawling
├── Crawling_wiki.py              # Wikipedia API crawling
├── credentials.json              # Institutional login credentials (gitignored)
├── wiki_data.json                # Wikipedia crawling results (JSON)
├── wiki_data.jsonl               # For vector databases (JSONL)
└── tiktoken/
    └── scripts/
        ├── pdf_token_counter.py
        └── json_token_counter.py
```

---

## IEEE TGRS Crawling Script

**File**: `crawling_ieee_2023_2025.py`

Downloads PDF papers from IEEE Xplore (Transactions on Geoscience and Remote Sensing)
through the Kookmin University library proxy.

### Modes

| Mode | Description |
|------|-------------|
| `linux` | **Headless** – for remote servers. Chrome runs silently in the background. |
| `windows` | **GUI** – for local Windows PCs. Browser window stays open so you can visually monitor every step and diagnose issues easily. |

### Quick Start

**1. Install dependencies**

```bash
pip install selenium webdriver-manager
```

**2. Set credentials** (`credentials.json`)

```json
{
  "univ_id": "your_student_id",
  "univ_pw": "your_password"
}
```

**3. Run**

```bash
# Linux server (headless)
python crawling_ieee_2023_2025.py --mode linux --years 2023 2024 2025

# Windows local PC (browser window visible)
python crawling_ieee_2023_2025.py --mode windows --years 2023 2024 2025

# Single year
python crawling_ieee_2023_2025.py --mode linux --year 2024

# Custom save path
python crawling_ieee_2023_2025.py --mode windows --year 2023 --save-path D:\MyPapers

# Pass credentials directly (without credentials.json)
python crawling_ieee_2023_2025.py --mode windows --year 2023 --username myid --password mypw
```

### All Options

```
--mode {linux,windows}    Execution mode (auto-detected from OS if omitted)
--year  INT               Single year to crawl (e.g. 2024)
--years INT [INT ...]     Multiple years (e.g. --years 2023 2024 2025)
--save-path PATH          Base directory for downloaded PDFs
--username STR            Library login ID
--password STR            Library login password
```

### Default Save Paths

| Mode    | Default Path |
|---------|-------------|
| linux   | `/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025` |
| windows | `C:\Users\<USERNAME>\Downloads\IEEE_TGRS` |

PDFs are saved under `<base-path>/<year>/`.

### Windows Tips

- The browser window opens automatically. You can see exactly what the script is doing.
- If login or navigation fails, you can observe the browser state to diagnose the problem.
- `webdriver-manager` automatically installs the matching ChromeDriver version.
- Make sure Chrome browser is installed before running.

---

## ScienceDirect Crawling

**File**: `Crawling_ScienceDirect.ipynb`

Downloads PDFs from Elsevier ScienceDirect.

**Configuration**:
```python
TITLE = "Remote Sensing of Environment"  # Journal name
SET_YEAR = "2001"                        # Year to crawl
START_PAGE = 1
MAX_PAGE_VISITS = 300
```

---

## Wikipedia Crawling

**File**: `Crawling_wiki.py`

Collects Wikipedia articles for HSI-related terms via the Wikipedia API.

```bash
python Crawling_wiki.py
```

**Output**:
- `wiki_data.json`: Full data with metadata
- `wiki_data.jsonl`: One document per line (for vector databases)

---

## Token Counting Tools

```bash
# PDF token count
python tiktoken/scripts/pdf_token_counter.py "file.pdf"
python tiktoken/scripts/pdf_token_counter.py "path/to/folder"

# JSON/JSONL token count
python tiktoken/scripts/json_token_counter.py "file.json"
python tiktoken/scripts/json_token_counter.py "file.json" --field "documents[].text"
```

---

## Dependencies

```bash
# Crawling
pip install selenium webdriver-manager
pip install pandas openpyxl tqdm

# Wikipedia
pip install wikipedia-api

# Token counting
pip install tiktoken pymupdf4llm pymupdf
```

---

## Notes

- Crawling goes through the Kookmin University library proxy (`proxy.kookmin.ac.kr`).
- Bulk downloads may trigger IEEE Seat Limit; the script waits and retries automatically.
- `credentials.json` is listed in `.gitignore` — never commit real credentials.
