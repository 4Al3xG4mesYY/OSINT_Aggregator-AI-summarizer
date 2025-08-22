# Project Synapse: An Automated Threat Intelligence Pipeline

## Overview
Project Synapse is a sophisticated, Python-based Open-Source Intelligence (OSINT) tool designed to automate the collection, processing, and reporting of cybersecurity news. It aggregates articles from multiple sources, including Google Alerts and RSS feeds, scrapes the full content of each article, and utilizes the Gemini AI API to generate concise summaries and extract key entities. The results are stored in a local SQLite database with a graph-like structure, preventing duplicates and allowing for relational analysis.

A key feature is the "human-in-the-loop" integration with Slack, which allows the tool to de-conflict its automated collection with the work of a human analysis team, ensuring efficiency and preventing duplicate efforts.

## Features
* **Multi-Source Collection:** Gathers intelligence from both Google Alerts (via the Gmail API) and a configurable list of RSS feeds.
* **Advanced Scraping Engine:**
    * **Browser Impersonation:** Uses `curl_cffi` to mimic a browser's TLS fingerprint, bypassing advanced anti-bot services like Cloudflare.
    * **Dynamic Content Handling:** Employs Selenium to control a headless Chrome browser, enabling the scraping of JavaScript-heavy websites.
* **AI-Powered Summarization & NER:** Leverages the Gemini API (`gemini-1.5-flash-latest`) to generate unique, two-sentence summaries and perform Named Entity Recognition (NER), automatically extracting threat actors, malware, and vulnerabilities.
* **Graph-Based Data Persistence:** Stores all processed articles, entities, and their relationships in an SQLite database, preventing duplication and building a network of interconnected intelligence.
* **"Data Healing" Workflow:** A `--retry-fallbacks` mode uses Selenium to re-process articles that failed during the initial, faster collection run, improving dataset quality over time.
* **Slack Integration:** Checks a designated Slack channel to see if an article has already been covered by a human analyst, saving their summary and avoiding redundant processing.
* **Organized Reporting:** Generates a clean `.txt` report with articles grouped by source and clear indicators for AI-generated vs. Slack-verified summaries.

## Tech Stack
* **Programming Language:** Python 3
* **Key Libraries:** `google-api-python-client`, `requests`, `newspaper3k`, `feedparser`, `curl_cffi`, `selenium`, `slack_sdk`, `sqlite3`
* **APIs:** Google Gmail API, Google Gemini API, Slack API

## Setup and Installation
1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  **Create and activate a Python virtual environment:**

    * **Linux/macOS:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    * **Windows:**
        ```powershell
        python -m venv venv
        .\venv\Scripts\Activate.ps1
        ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration
Before running, configure your API credentials. For security, store your keys in a `.env` file.

1.  Create a `.env` file in the project root.
2.  Add your API keys:
    ```
    GEMINI_API_KEY=YOUR_GEMINI_API_KEY
    SLACK_BOT_TOKEN=YOUR_SLACK_BOT_TOKEN
    SLACK_CHANNEL_ID=YOUR_SLACK_CHANNEL_ID
    ```
3.  Obtain your `credentials.json` for Gmail API access from Google Cloud Console, and place it in the root directory.

## Usage
### Normal Run (collect new articles)
* **Linux/macOS:**
    ```bash
    ./osint_aggregator.py "Ransomware" "Malware"
    ```
* **Windows:**
    ```powershell
    python osint_aggregator.py "Ransomware" "Malware"
    ```

### Re-processing Run (retry failed scrapes with Selenium)
* **Linux/macOS:**
    ```bash
    ./osint_aggregator.py --retry-fallbacks
    ```
* **Windows:**
    ```powershell
    python osint_aggregator.py --retry-fallbacks
    ```

## Real-World Challenges & Lessons Learned
* **API Rate Limiting:** Early Gemini API calls caused `429: RESOURCE_EXHAUSTED` errors. Solution: added `time.sleep()` delays to respect rate limits.
* **Anti-Scraping Measures:** Encountered `403` errors on many sites. Developed a robust scraper with rotating User-Agent strings and `curl_cffi` impersonation.
* **Data Integrity & Concurrency:** Facing `database is locked` errors initially. Resolved by managing database connections carefully and refactoring to sequential operations.

## Project Evolution Timeline
* **Phase 1: The Proof of Concept (Local Scraper)**
    * Basic script parsing a manually saved email with `BeautifulSoup`.
* **Phase 2: Automation & Intelligence (API Integrator)**
    * Integrated Gmail API and Gemini API for summarization.
* **Phase 3: Resilience & Expansion (Robust Aggregator)**
    * Added SQLite database and RSS feeds; upgraded scraper with `curl_cffi`.
* **Phase 4: The Collaborative Platform (Human-in-the-Loop)**
    * Slack integration and Selenium-based "Data Healing" mode to re-collect difficult sites.
* **Phase 5: The Intelligence Platform (Graph Database)**
    * Re-architected database into a graph model; added NER to build interconnected threat networks.

## 🛠️ Next Steps & Future Upgrades
* **Secrets Management:** Migrate all API keys and tokens to a secure `.env` file for better security.
* **Interactive Graph Visualization:** Use `pyvis` or `Dash Cytoscape` to visualize threat actor and malware relationships within a Flask dashboard.
* **Full Automation:** Set up Windows Task Scheduler or `cron` jobs for scheduled, unattended runs.
* **Slack Bot Integration:** Re-architect into a web app (using Flask or FastAPI) to support slash commands (`/osint-collect`, `/osint-report`) for team interaction.

---
This README provides a comprehensive guide to deploying and evolving Project Synapse into a resilient, automated OSINT platform.
