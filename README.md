# OSINT Aggregator & AI Summarizer

## Overview

This project is a Python-based Open-Source Intelligence (OSINT) tool designed to automate the collection and processing of cybersecurity news. It aggregates articles from multiple sources, including custom Google Alerts and RSS feeds, scrapes the full content of each article, and utilizes the Gemini AI API to generate concise, two-sentence summaries. The results are stored in a local SQLite database to prevent duplicates and are compiled into a clean, organized daily intelligence briefing.

A key feature is the "human-in-the-loop" integration with Slack, which allows the tool to de-conflict its automated collection with the work of a human analysis team, preventing duplicate efforts.

## Features

* **Multi-Source Collection:** Gathers intelligence from both Google Alerts (via the Gmail API) and a configurable list of RSS feeds.
* **Advanced Scraping Engine:**
    * **Browser Impersonation:** Uses `curl_cffi` to mimic a browser's TLS fingerprint, bypassing advanced anti-bot services like Cloudflare.
    * **Dynamic Content Handling:** Employs **Selenium** to control a headless Chrome browser, enabling the scraping of JavaScript-heavy websites.
* **AI-Powered Summarization:** Leverages the Gemini API (`gemini-1.5-flash-latest`) to generate unique, two-sentence summaries of article content.
* **Data Persistence & Deduplication:** Stores all processed articles in an SQLite database, preventing duplicate entries in the final report.
* **"Data Healing" Workflow:** A `--retry-fallbacks` mode uses the powerful Selenium scraper to re-process articles that failed during the initial, faster collection run, improving the quality of the dataset over time.
* **Slack Integration:** Checks a designated Slack channel to see if an article has already been covered by a human analyst. If so, it saves the human-written summary and skips automated processing.
* **Organized Reporting:** Generates a clean `.txt` report with articles grouped by source and clear indicators for AI-generated vs. Slack-verified summaries.

## Tech Stack

* **Programming Language:** Python 3
* **Key Libraries:** `google-api-python-client`, `requests`, `newspaper3k`, `feedparser`, `curl_cffi`, `selenium`, `slack_sdk`, `sqlite3`
* **APIs:** Google Gmail API, Google Gemini API, Slack API

## Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  **Create and activate a Python virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies from `requirements.txt`:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Before running, you must configure your API credentials:

1.  **Gmail API Credentials:** Follow Google's documentation to create an OAuth 2.0 Client ID. Download the file and rename it to `credentials.json`.
2.  **Gemini API Key:** Generate a free API key from [Google AI Studio](https://aistudio.google.com/) and paste it into the `api_key` variable in the script.
3.  **Slack API Token:** Create a Slack App, grant it the `channels:history` and `channels:read` scopes, and get a Bot User OAuth Token and the Channel ID. Paste these into the `SLACK_CONFIG` section of the script.

**Important:** For security, it is highly recommended to store your keys in a `.env` file and use a library like `python-dotenv` to load them, rather than pasting them directly into the script.

## Usage

Make the script executable (one-time setup):
```bash
chmod +x google_alert_scraper_api.py
```

**Normal Run (collect new articles):**
```bash
./google_alert_scraper_api.py "Ransomware" "Malware"
```
## Project Evolution Timeline: From Simple Script to OSINT Platform

This timeline documents the journey of the OSINT Aggregator, showing its evolution from a basic, single-purpose script into a resilient, multi-source intelligence platform with a collaborative, "human-in-the-loop" workflow.

---

### Phase 1: The Proof of Concept (The Local Scraper)

**Goal:**  
Prove that it was possible to parse a Google Alert email and reformat the content.

**Features:**
- Reads a single, manually downloaded `.eml` file from the local disk.
- Uses BeautifulSoup to parse the email's HTML structure.
- Extracts the title, URL, and snippet for each news item.
- Writes the formatted results to a `.txt` file, overwriting it on each run.

**Technologies:**  
`Python`, `BeautifulSoup4`, `lxml`

**Limitations:**
- **Manual Workflow:** Required the user to download an email for every run.
- **Fragile Parsing:** Relied on a specific HTML structure that could break if Google changed their email layout.
- **No Memory:** Could not remember previously processed articles, leading to duplicate work.

---

### Phase 2: Automation & Intelligence (The API Integrator)

**Goal:**  
Automate the collection process and improve the quality of the intelligence with AI.

**Features Added:**
- **Gmail API Integration:** Automatically and securely fetched the latest Google Alert emails directly from the inbox using OAuth 2.0.
- **Article Scraping:** Used the `newspaper3k` library to visit each article's URL and extract the full text and the original publication date.
- **AI Summarization:** Integrated the Gemini AI API to read the full article text and generate a unique, two-sentence summary.

**Technologies Added:**  
`google-api-python-client`, `newspaper3k`, `requests` (for Gemini API)

**Limitations:**
- **Scraping Failures:** Many websites blocked the basic scraper, resulting in 403 Forbidden errors.
- **API Errors:** The script was vulnerable to temporary network issues and API rate limits, causing it to fail.
- **Still No Memory:** The duplicate article problem remained unsolved.

---

### Phase 3: Resilience & Expansion (The Robust Aggregator)

**Goal:**  
Make the tool more reliable, expand its sources, and solve the data duplication problem.

**Features Added:**
- **Database Integration:** Implemented an SQLite database to store all processed articles, creating a persistent intelligence library.
- **Data Deduplication:** The script now checks the database before processing any article, skipping duplicates and making subsequent runs highly efficient.
- **RSS Feed Collection:** Added the `feedparser` library to pull articles from multiple, configurable RSS feeds, turning the tool into a true multi-source aggregator.
- **Advanced Scraping:** Upgraded the scraper to use `curl_cffi` to impersonate a browser's TLS fingerprint, bypassing many anti-bot services.
- **Error Handling:** Implemented automatic retries with an exponential backoff for failed scrapes and API calls.

**Technologies Added:**  
`sqlite3`, `feedparser`, `curl_cffi`

**Limitations:**
- **Dynamic Websites:** The scraper still failed on complex websites that load their content with JavaScript.
- **"Stale" Data:** Articles that failed to scrape were stuck with a lower-quality fallback summary forever.
- **No Team Integration:** The tool worked in isolation and had no awareness of what a human team was already working on.

---

### Phase 4: The Final Product (The Collaborative Platform)

**Goal:**  
Create a "final product" that can handle the most difficult websites and integrate with a real-world team workflow.

**Features Added:**
- **"Data Healing" Workflow:** A new `--retry-fallbacks` mode was created to re-process articles that had previously failed.
- **Selenium Integration:** The "data healing" mode uses Selenium to control a headless Chrome browser, allowing it to successfully scrape JavaScript-heavy websites that were previously impossible to access.
- **Slack Integration:** The script now connects to a designated Slack channel to check if an article has already been covered by a human analyst. If so, it uses the human-written summary and marks the article as `[VERIFIED BY SLACK]`, preventing duplicate work.
- **Professional Polish:** Added a timer for performance metrics, organized the final report with clear headers, and created professional documentation (`README.md`, `requirements.txt`).

**Technologies Added:**  
`selenium`, `slack_sdk`

**Result:**  
A complete, resilient, and collaborative OSINT platform ready for automated deployment.
```

---
**How to use**:  
Just copy everything between the triple-backticks (````markdown ... ```
No further editing required—Markdown parsers will render headers, bullet points, and emphasis for you.


**Re-processing Run (retry failed scrapes with Selenium):**
```bash
./google_alert_scraper_api.py --retry-fallbacks
