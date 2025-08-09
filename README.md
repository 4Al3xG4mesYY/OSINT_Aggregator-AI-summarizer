# Project Synapse: An Automated Threat Intelligence Pipeline

## Overview

Project Synapse is a sophisticated Open-Source Intelligence (OSINT) pipeline designed for cybersecurity professionals. It automates the collection, analysis, and reporting of threat intelligence by replacing manual workflows with an integrated system. The core of the platform is a robust Scrapy engine that uses a hybrid scraping approach: quickly discovering new articles from RSS feeds and then performing deep, full-text scraping on each to get rich data. The collected intelligence is processed by the Gemini AI API for summarization and is then stored in a centralized PostgreSQL database using SQLAlchemy for data integrity and multi-user access. The platform's final output is a clean intelligence briefing that is de-conflicted with the work of a human team through an elegant "human-in-the-loop" workflow with Slack.

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

## Challenges & Lessons Learned

This project involved overcoming several real-world development challenges, providing valuable lessons in building resilient applications.

* **Database Migration & Concurrency:** The project successfully migrated from a simple, local SQLite database to a production-ready PostgreSQL database. This required refactoring all data persistence logic to use SQLAlchemy, which ensures data integrity and supports concurrent access from multiple users or processes.

* **Import Path Issues:** The move to a separated Scrapy project led to persistent ModuleNotFoundError errors. This was resolved by mastering the use of the PYTHONPATH environment variable, which is a critical skill for building professional, multi-module applications.

* **API Integration:** We successfully implemented and integrated the Google Gmail and Gemini APIs, ensuring that API keys are managed securely as environment variables and that API calls are robustly handled with retry mechanisms.

* **Hybrid Scraping Architecture:** We moved from a brittle, single-method scraping approach to a powerful hybrid model that leverages fast RSS feeds for discovery and dedicated Scrapy spiders for robust, full-text HTML scraping.

---

# Project Evolution Timeline

This timeline documents the journey of Project Synapse, showing its evolution from a basic, single-purpose script into a resilient, multi-source intelligence platform with a collaborative, "human-in-the-loop" workflow.

### Phase 1: The Proof of Concept (The Local Scraper)

* **Goal:** Prove that it was possible to parse a Google Alert email and reformat the content.
* **Features:** Read a single, manually saved `.eml` file and used BeautifulSoup to parse the HTML.
* **Technologies:** Python, BeautifulSoup4, lxml
* **Limitations:** Manual workflow, fragile parsing, and no memory (duplicates).

### Phase 2: Refactoring for Scalability (The SQLAlchemy Migration)

* **Goal:** Solve the data persistence problem by migrating to a professional, multi-user database.
* **Features Added:** All database interaction was refactored from sqlite3 to SQLAlchemy. A PostgreSQL database was installed and configured as the new central data store.
* **Technologies Added:** sqlalchemy, psycopg2-binary, pgadmin4
* **Lessons Learned:** This phase taught the importance of a clean database schema and the challenge of migrating from file-based sqlite to a client-server PostgreSQL system. We overcame UndefinedColumn and permission denied errors by correctly configuring the database and ensuring the script's create_tables() function was properly executed.

### Phase 3: The Robust Scraping Engine (Scrapy Integration)

* **Goal:** Replace the brittle, ad-hoc scraping methods with a powerful, resilient framework.
* **Features Added:** The old requests and feedparser loops were replaced with a Scrapy project. A hybrid scraping pipeline was implemented to quickly parse RSS feeds and then perform a deep scrape on the full article pages.
* **Technologies Added:** scrapy
* **Lessons Learned:** This phase highlighted a key challenge in integrating external Python projects: ModuleNotFoundError. We solved this by mastering the use of the PYTHONPATH environment variable, which is a critical skill for building professional, multi-module applications.

### Phase 4: The Collaborative Platform (The "Human-in-the-Loop" Tool) <-- We working on here

* **Goal:** Automate AI analysis, get team feedback, and handle the most difficult websites.
* **Features Added:** The Gemini AI API was integrated into the Scrapy pipeline, and a new Flask-based Slack app was created. The Slack integration allows for team collaboration via slash commands and for a "human-in-the-loop" workflow.
* **Technologies Added:** flask, slack_sdk, gunicorn
* **Lessons Learned:** This phase taught the importance of API permissions (missing_scope) and how to build a robust web application that can handle long-running tasks without timing out (dispatch_failed).

### 🛠️ Next Steps & Future Upgrades

The project is now a complete, professional threat intelligence platform. The next steps are focused on professionalizing its deployment and enhancing the user's ability to analyze the collected data.

* **Professional Deployment (High Priority):** Containerize the application using Docker. This will ensure that the application runs in a consistent environment, and it will allow for easy deployment to cloud platforms like Oracle Cloud or Render using a production-ready web server like Gunicorn.
* **Secrets Management:** Move all API keys (Gemini, Slack) and database credentials out of the Python script and into a secure .env file. This is a critical security best practice to prevent accidentally exposing secrets.
* **Interactive Graph Visualization:** The database now contains a rich network of interconnected intelligence. The next major step would be to use a library like pyvis or Dash Cytoscape to create a new page on a Flask dashboard that visually represents the connections between threat actors, malware, and articles, allowing for interactive analysis.
* **Full Automation with Cron:** Implement a cron job to run the script on a set schedule (e.g., daily) for a true, unattended intelligence feed.
