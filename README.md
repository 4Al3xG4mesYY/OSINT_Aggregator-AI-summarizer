# Project Synapse: An Automated Threat Intelligence Pipeline

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
chmod +x osint_aggregator.py
```

**Normal Run (collect new articles):**
```bash
./osint_aggregator.py "Ransomware" "Malware"
```

**Re-processing Run (retry failed scrapes with Selenium):**
```bash
./osint_aggregator.py --retry-fallbacks
```

---

## Project Evolution Timeline

This timeline documents the journey of Project Synapse, showing its evolution from a basic, single-purpose script into a resilient, multi-source intelligence platform with a collaborative, "human-in-the-loop" workflow.

### Phase 1: The Proof of Concept (The Local Scraper)

* **Goal:** Prove that it was possible to parse a Google Alert email and reformat the content.
* **Features:** Read a single, manually saved `.eml` file and used `BeautifulSoup` to parse the HTML.
* **Technologies:** `Python`, `BeautifulSoup4`, `lxml`
* **Limitations:** Manual workflow, fragile parsing, and no memory (duplicates).

### Phase 2: Automation & Intelligence (The API Integrator)

* **Goal:** Automate collection and improve intelligence quality with AI.
* **Features Added:** Integrated the Gmail API, used `newspaper3k` for article scraping, and added the Gemini AI API for summarization.
* **Technologies Added:** `google-api-python-client`, `newspaper3k`, `requests`
* **Limitations:** Suffered from scraping failures, API errors, and still had no way to avoid duplicates.

### Phase 3: Resilience & Expansion (The Robust Aggregator)

* **Goal:** Make the tool reliable, expand its sources, and solve the data duplication problem.
* **Features Added:** Implemented an SQLite database for persistence and deduplication, added RSS feed collection, and upgraded the scraper with `curl_cffi` and automatic retries.
* **Technologies Added:** `sqlite3`, `feedparser`, `curl_cffi`
* **Limitations:** Still failed on JavaScript-heavy websites and had no awareness of a human team's workflow.

### Phase 4: The Collaborative Platform (The "Human-in-the-Loop" Tool)

* **Goal:** Handle the most difficult websites and integrate with a real-world team workflow.
* **Features Added:** A "Data Healing" mode using **Selenium** to re-process failed scrapes, and **Slack Integration** to de-conflict with manual analysis.
* **Technologies Added:** `selenium`, `slack_sdk`
* **Result:** A complete, resilient, and collaborative OSINT platform ready for automated deployment.

### Phase 5: The Intelligence Platform (The Graph Database)

* **Goal:** Transform the data from a simple list into a network of interconnected intelligence.
* **Features Added:** Re-architected the SQLite database to use a **graph data model** (with `articles`, `entities`, and `relationships` tables). Upgraded the AI prompt to perform **Named Entity Recognition (NER)**, automatically extracting threat actors, malware, and vulnerabilities to build the intelligence graph.
