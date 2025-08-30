# Project Synapse: An Automated Threat Intelligence Pipeline
**An advanced OSINT tool that automatically collects and analyzes cybersecurity articles, building an interactive graph of interconnected threats, malware, and vulnerabilities.**

## Overview
Project Synapse is a sophisticated, Python-based Open-Source Intelligence (OSINT) tool designed to automate the collection, processing, and analysis of cybersecurity intelligence. It aggregates articles from Google Alerts and RSS feeds, scrapes the full content, and utilizes the Gemini AI API to generate concise summaries, assess severity, and perform Named Entity Recognition (NER).

All processed data is stored in a local SQLite database with a graph-like structure, allowing for powerful relational analysis. The project includes separate modules for generating professional HTML reports and interactive graph visualizations, transforming raw news into a network of interconnected intelligence.

## Features
* **Multi-Source Collection**: Gathers intelligence from both Google Alerts (via the Gmail API) and a configurable list of cybersecurity RSS feeds.
* **Advanced Scraping Engine**:
    * **Browser Impersonation**: Uses `curl_cffi` to mimic a browser, bypassing advanced anti-bot services like Cloudflare.
    * **Dynamic Content Handling**: Employs Selenium to control a headless Chrome browser for scraping JavaScript-heavy websites.
* **AI-Powered Analysis**: Leverages the Gemini AI API (`gemini-1.5-flash-latest`) for three key tasks:
    * **Summarization**: Generates unique, two-sentence summaries.
    * **Severity Assessment**: Assigns a "High," "Medium," or "Low" severity rating to each article.
    * **Entity Extraction (NER)**: Automatically extracts and links threat actors, malware families, and CVE vulnerabilities.
* **Graph-Based Intelligence Database**: Stores articles, entities, and their relationships in an SQLite database, building a powerful network of interconnected threat intelligence.
* **Interactive Graph Visualization**: Includes a `visualize_graph.py` script that uses `pyvis` and `networkx` to generate an interactive HTML graph, allowing for visual analysis of threat relationships.
* **Automated HTML Reporting**: Comes with a `report_generator.py` script that creates a professional, weekly HTML report with articles grouped by severity.
* **"Data Healing" Workflow**: A `--retry-fallbacks` mode uses the more robust Selenium engine to re-process articles that failed during the initial, faster collection run, improving dataset quality over time.
* **Secure Credential Management**: All API keys are securely managed outside of the codebase using a `.env` file.

## Tech Stack
* **Programming Language:** Python 3
* **Key Libraries:** `google-api-python-client`, `requests`, `newspaper3k`, `feedparser`, `curl_cffi`, `selenium`, `slack_sdk`, `sqlite3`, `selenium`, `tqdm`, `jinja2`, `pyvis`, `networkx`
* **APIs:** Google Gmail API, Google Gemini API

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
    ```
3.  Obtain your `credentials.json` for Gmail API access from Google Cloud Console, and place it in the root directory.

## Usage
The script is run from the command line and has two primary modes.

### Normal Run (Collect New Articles)
This command fetches all recent Google Alert digests and RSS feed articles.
* **Linux/macOS:**
    ```bash
    python3 osint_aggregator.py
    ```
* **Windows:**
    ```powershell
    python osint_aggregator.py
    ```
* **Verbose Mode (for Debugging):**
Add the `--verbose` flag to see detailed error messages for scraping or AI analysis failures.
    ```bash
    python3 osint_aggregator.py --verbose
    ```

### Re-processing Run ("Data Healing")
This command retries any articles that previously failed to scrape correctly, using the more robust Selenium engine.
* **Linux/macOS:**
    ```bash
    python3 osint_aggregator.py --retry-fallbacks
    ```
* **Windows:**
    ```powershell
    python osint_aggregator.py --retry-fallbacks
    ```
  
## Generate Reports
* **Generate the HTML and JSON reports**
    ```
    python report_generator.py
    ```
* **Generate the interactive graph visualization**
    ```
    python visualize_graph.py
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
* **Advanced Graph Queries:** Build new modules to perform complex queries on the graph database, such as identifying the most active threat actors or co-occurring malware families.
* **Web Dashboard:** Create a web front-end using Flask or FastAPI to display the HTML report and embed the interactive graph visualization.
* **Full Automation:** Set up cron jobs (Linux/macOS) or Task Scheduler (Windows) for scheduled, unattended runs of the aggregator.
* **Slack Bot Integration:** Develop the aggregator into a web app to support Slack slash commands (/osint-collect, /osint-report) for team interaction.

---
This README provides a comprehensive guide to deploying and evolving Project Synapse into a resilient, automated OSINT platform.
