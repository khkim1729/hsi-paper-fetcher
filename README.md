# hsi-paper-fetcher

A collection of crawling tools for downloading Hyperspectral Imaging (HSI) research papers and related data.

> **[한국어 문서 (Korean)](README_ko.md)**

---

## Project Structure

```
hsi-paper-fetcher/
├── crawling_ieee_2023_2025.py    # IEEE TGRS bulk PDF downloader (main script)
├── Crawling_IEEE_year.ipynb      # IEEE year-based crawling (notebook)
├── Crawling_ScienceDirect.ipynb  # ScienceDirect crawling
├── Crawling_wiki.py              # Wikipedia API crawling
├── credentials.json              # Institutional login credentials (gitignored)
├── wiki_data.json                # Wikipedia crawling results
├── wiki_data.jsonl               # For vector databases (JSONL)
└── tiktoken/scripts/
    ├── pdf_token_counter.py
    └── json_token_counter.py
```

---

## IEEE TGRS Crawling (`crawling_ieee_2023_2025.py`)

### Flow

```
[Step 1] Login to Kookmin University Library
  URL    : https://lib.kookmin.ac.kr/login?returnUrl=%3F&queryParamsHandling=merge
  ID/PW  : loaded from credentials.json

      ↓

[Step 2] Navigate to IEEE database page
  URL    : https://lib.kookmin.ac.kr/search/database?keyword=IEEE
  Action : Click IEEE link → new window opens (IEEE Xplore via proxy)
  Switch : Automatically switches to the new window

      ↓

[Step 3] IEEE Advanced Search
  - Enter Start Year / End Year
  - Run search

      ↓

[Step 4] Journal filter
  - Select "IEEE Transactions on Geoscience and Remote Sensing"

      ↓

[Step 5] Bulk PDF download per page
  - Select All → Download → PDF → Confirm
  - Navigate to next page and repeat
  - Auto wait & retry on Seat Limit
```

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
# GUI mode (browser window visible – easy to monitor and debug)
python crawling_ieee_2023_2025.py --years 2023 2024 2025

# Headless mode (server environment)
python crawling_ieee_2023_2025.py --headless --years 2023 2024 2025

# Single year
python crawling_ieee_2023_2025.py --year 2024

# Custom save path
python crawling_ieee_2023_2025.py --year 2023 --save-path /my/papers

# Pass credentials directly
python crawling_ieee_2023_2025.py --year 2023 --username myid --password mypw
```

### Options

| Option | Description |
|--------|-------------|
| `--headless` | Run Chrome without a visible window (server mode) |
| `--year INT` | Single year (e.g. `--year 2024`) |
| `--years INT...` | Multiple years (e.g. `--years 2023 2024 2025`) |
| `--save-path PATH` | Base directory for downloaded PDFs |
| `--username STR` | Library login ID |
| `--password STR` | Library login password |

### Default Save Paths

| OS | Path |
|----|------|
| Linux | `/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025/<year>/` |
| Windows | `C:\Users\<USERNAME>\Downloads\IEEE_TGRS\<year>\` |

---

## ScienceDirect Crawling

**File**: `Crawling_ScienceDirect.ipynb`

```python
TITLE = "Remote Sensing of Environment"
SET_YEAR = "2001"
START_PAGE = 1
MAX_PAGE_VISITS = 300
```

---

## Wikipedia Crawling

```bash
python Crawling_wiki.py
```

Output: `wiki_data.json`, `wiki_data.jsonl`

---

## Token Counting

```bash
python tiktoken/scripts/pdf_token_counter.py "file.pdf"
python tiktoken/scripts/json_token_counter.py "file.json"
```

---

## Notes

- `credentials.json` is gitignored and will never be committed.
- Seat Limit is handled automatically with 5-minute wait and retry.
- `webdriver-manager` handles ChromeDriver version matching automatically.
