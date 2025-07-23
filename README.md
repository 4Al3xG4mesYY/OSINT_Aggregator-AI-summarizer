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

**Re-processing Run (retry failed scrapes with Selenium):**
```bash
./google_alert_scraper_api.py --retry-fallbacks
