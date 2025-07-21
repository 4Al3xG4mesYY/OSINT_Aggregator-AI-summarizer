# OSINT Aggregator & AI Summarizer

## Overview

This project is a Python-based Open-Source Intelligence (OSINT) tool designed to automate the collection and processing of cybersecurity news. It aggregates articles from multiple sources, including custom Google Alerts and RSS feeds, scrapes the full content of each article, and utilizes the Gemini AI API to generate concise, two-sentence summaries. The results are stored in a local SQLite database to prevent duplicates and are compiled into a clean, organized daily intelligence briefing.

This tool was developed to streamline the threat intelligence workflow, providing a rapid, automated way to stay informed on emerging threats, vulnerabilities, and cyber events.

## Features

* **Multi-Source Collection:** Gathers intelligence from both Google Alerts (via the Gmail API) and a configurable list of RSS feeds.
* **Intelligent Scraping:** Employs the `newspaper3k` library to extract clean article text and metadata, with built-in retries and rotating user-agents to handle anti-scraping measures.
* **AI-Powered Summarization:** Leverages the Gemini API (`gemini-1.5-flash-latest`) to generate unique, two-sentence summaries of article content, with a graceful fallback to email snippets if scraping or AI fails.
* **Data Persistence & Deduplication:** Stores all processed articles in an SQLite database, preventing duplicate entries in the final report.
* **Organized Reporting:** Generates a clean `.txt` report with articles grouped by their intelligence source (e.g., "Google Alert: Ransomware", "RSS: Bleeping Computer").
* **Resilient & Professional:** Includes robust error handling, API rate-limit management, and secure authentication via OAuth 2.0.

## Tech Stack

* **Programming Language:** Python 3
* **Key Libraries:**
    * `google-api-python-client`: For interacting with the Gmail API.
    * `requests`: For synchronous HTTP requests to the Gemini API.
    * `newspaper3k`: For article scraping and content extraction.
    * `feedparser`: For parsing RSS feeds.
    * `BeautifulSoup4` & `lxml`: For HTML parsing.
    * `nltk`: For natural language processing tasks required by `newspaper3k`.
    * `sqlite3`: For database storage.
* **APIs:**
    * Google Gmail API
    * Google Gemini API

## Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  **Create a Python virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib beautifulsoup4 lxml newspaper3k nltk lxml_html_clean requests feedparser
    ```

## Configuration

Before running the script, you must configure three things:

1.  **Gmail API Credentials:** Follow Google's documentation to create an OAuth 2.0 Client ID. Download the resulting JSON file and rename it to `credentials.json` in the project's root directory.
2.  **Gemini API Key:** Generate a free API key from [Google AI Studio](https://aistudio.google.com/). Open `google_alert_scraper_api.py` and paste your key into the `api_key` variable.
3.  **RSS Feeds (Optional):** Open `google_alert_scraper_api.py` and add or remove URLs from the `RSS_FEEDS` dictionary.

## Usage

Run the script from the command line, providing one or more Google Alert keywords as arguments.

```bash
python google_alert_scraper_api.py "Ransomware" "Critical Infrastructure" "Malware"
```

The script will process all sources and generate an `osint_database.db` file and a `scraped_alerts.txt` report.

## Future Improvements

* **Full Automation with Cron:** The next major step is to implement a `cron` job to run the script on a set schedule (e.g., daily) for a true, unattended intelligence feed.
* **Named Entity Recognition (NER):** Integrate a library like `spaCy` to automatically extract key entities from articles, such as malware names, threat actor groups, and victim organizations.
* **HTML Reporting:** Upgrade the output from a `.txt` file to a more professional and interactive HTML report.
* **External Configuration:** Move API keys, keywords, and RSS feeds into a separate `config.ini` file to make the tool easier to manage and more secure.
