#!/usr/bin/env python
# osint_aggregator.py (Project Synapse)

# This is the unified OSINT aggregator. It fetches Google Alert digests and
# RSS feeds, performs AI summarization using the reliable JSON markup method,
# and stores results in a local SQLite graph database.
#
# How to Use (Windows):
# 1. Activate venv: venv\Scripts\activate
# 2. Normal Run: python osint_aggregator.py
# 3. Retry Run:  python osint_aggregator.py --retry-fallbacks

import base64
import email
import json
import os.path
import sys
import time
from email import policy
from urllib.parse import parse_qs, urlparse
from datetime import datetime
import sqlite3
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from dotenv import load_dotenv

import requests
import feedparser
import nltk
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from newspaper import Article, ArticleException
from curl_cffi import requests as curl_requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from tqdm import tqdm

# --- CONFIGURATION ---

RSS_FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "Bleeping Computer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "Dark Reading": "https://www.darkreading.com/rss_simple.asp",
    "Wired - Security": "https://www.wired.com/feed/category/security/latest/rss",
    "CSO Online": "https://www.csoonline.com/feed/",
    "SecurityWeek": "http://feeds.feedburner.com/Securityweek",
    "Ransomware Live": "https://www.ransomware.live/rss",
    "Malwarebytes Labs": "https://www.malwarebytes.com/blog/feed"
}

DB_FILE = "osint_database.db"
RETRY_CONFIG = {"max_retries": 2, "initial_delay": 5}

processing_stats = {
    'total_processed': 0,
    'ai_success': 0,
    'fallback_summary': 0,
    'skipped_duplicate': 0,
}

# --- DATABASE SETUP (Functions remain unchanged) ---

def setup_database():
    """Creates/updates the database to support a graph-like structure."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT,
            source_name TEXT NOT NULL,
            summary TEXT,
            source_indicator TEXT NOT NULL,
            category TEXT,
            severity TEXT,
            publish_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            UNIQUE(name, type)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS relationships (
            article_id INTEGER,
            entity_id INTEGER,
            FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE,
            FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
            PRIMARY KEY (article_id, entity_id)
        )
    ''')
    conn.commit()
    conn.close()

def is_url_in_db(url):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM articles WHERE url = ?", (url,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_entity(name, entity_type):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM entities WHERE name = ? AND type = ?", (name, entity_type))
    result = cursor.fetchone()
    if result:
        conn.close()
        return result[0]
    else:
        cursor.execute("INSERT INTO entities (name, type) VALUES (?, ?)", (name, entity_type))
        entity_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return entity_id

def link_article_to_entity(article_id, entity_id):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO relationships (article_id, entity_id) VALUES (?, ?)", (article_id, entity_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

def add_article_to_db(article_data, entities=None):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO articles (url, title, source_name, summary, source_indicator, category, severity, publish_date)
               VALUES (:url, :title, :source_name, :summary, :source_indicator, :category, :severity, :publish_date)""",
            article_data
        )
        article_id = cursor.lastrowid
        conn.commit()
        if entities and article_id:
            for entity_type, entity_list in entities.items():
                if entity_list:
                    for entity_name in entity_list:
                        entity_id = add_entity(entity_name, entity_type)
                        link_article_to_entity(article_id, entity_id)
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

def update_article_in_db(article_data, entities=None):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE articles SET
               title = :title, summary = :summary, source_indicator = :source_indicator,
               category = :category, severity = :severity, publish_date = :publish_date
           WHERE url = :url""",
        article_data
    )
    conn.commit()
    cursor.execute("SELECT id FROM articles WHERE url = ?", (article_data['url'],))
    result = cursor.fetchone()
    if result:
        article_id = result[0]
        cursor.execute("DELETE FROM relationships WHERE article_id = ?", (article_id,))
        conn.commit()
        if entities:
            for entity_type, entity_list in entities.items():
                if entity_list:
                    for entity_name in entity_list:
                        entity_id = add_entity(entity_name, entity_type)
                        link_article_to_entity(article_id, entity_id)
    conn.close()

# --- NLTK, AUTH, AND SCRAPING (Functions remain unchanged) ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                sys.exit("\nERROR: `credentials.json` not found.")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    try:
        return build('gmail', 'v1', credentials=creds)
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

def handle_http_error(error):
    try:
        status_code = error.resp.status
        if status_code == 400: print("  > [HTTP 400] Bad Request: The Gmail API query may be malformed.")
        elif status_code == 401: print("  > [HTTP 401] Unauthorized: Credentials are invalid. Delete 'token.json' and re-authenticate.")
        elif status_code == 403: print("  > [HTTP 403] Forbidden: API usage quota exceeded or Gmail API not enabled.")
        else: print(f"  > An unhandled HTTP error occurred: {error}")
    except AttributeError: print(f"  > An unexpected error occurred: {error}")

@retry(retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError)), stop=stop_after_attempt(RETRY_CONFIG["max_retries"]), wait=wait_fixed(RETRY_CONFIG["initial_delay"]))
def analyze_article_with_gemini(text):
    if not text or len(text.strip()) < 100: return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key: sys.exit("\nERROR: GEMINI_API_KEY not set in .env file.")
    categories = ["Malware Analysis", "Vulnerability Disclosure", "Threat Actor Profile", "Data Breach Report", "Geopolitical Cyber Event", "General Cyber News"]
    prompt = f"""Act as a Cyber Threat Intelligence Analyst. Analyze the following article.
    Provide your response as a single, valid JSON object with the following keys:
    - "summary": A two-sentence summary for a social media post.
    - "category": Classify the article into ONE of the following: {', '.join(categories)}.
    - "severity": Classify the threat's priority for a SOC analyst as "High", "Medium", or "Low".
    - "threat_actors": An array of any threat actor groups mentioned. If none, provide an empty array [].
    - "malware": An array of any malware families mentioned. If none, provide an empty array [].
    - "vulnerabilities": An array of any CVE identifiers mentioned. If none, provide an empty array [].

    Article:
    ---
    {text}
    """
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}",
            json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
            timeout=60)
        response.raise_for_status()
        result = response.json()
        if result.get('candidates'):
            content = result['candidates'][0]['content']['parts'][0]['text']
            clean_content = content.strip().replace('```json', '').replace('```', '')
            return json.loads(clean_content)
        return None
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e: raise

def scrape_article_details(url):
    try:
        response = curl_requests.get(url, impersonate="chrome110", timeout=60)
        response.raise_for_status()
        article = Article(url)
        article.set_html(response.content)
        article.parse()
        if not article.text or len(article.text.strip()) < 100: raise ArticleException("Content too short")
        return article.text, article.publish_date
    except Exception as e: raise

def scrape_with_selenium(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(5)
        article = Article(url)
        article.set_html(driver.page_source)
        article.parse()
        if not article.text or len(article.text.strip()) < 100: raise ArticleException("Content too short")
        return article.text, article.publish_date
    except Exception as e: raise
    finally:
        if driver: driver.quit()

# --- ADJUSTED GOOGLE ALERT AND PROCESSING LOGIC ---

def process_article(source_name, title, url, description, default_date, is_retry=False, verbose=False):
    processing_stats['total_processed'] += 1
    if not is_retry and is_url_in_db(url):
        processing_stats['skipped_duplicate'] += 1
        return
    article_text, publish_date = None, None
    try:
        if is_retry: article_text, publish_date = scrape_with_selenium(url)
        else: article_text, publish_date = scrape_article_details(url)
    except Exception as e:
        if verbose: print(f"  > Scraping failed for {url}: {e}")
        article_text = f"{title} - {description}"
    ai_analysis = None
    try:
        ai_analysis = analyze_article_with_gemini(article_text)
    except Exception as e:
        if verbose: print(f"  > AI analysis failed for {url}: {e}")
    effective_date = publish_date if publish_date else default_date
    date_str = effective_date.isoformat() if effective_date else None
    article_data = {"url": url, "title": title, "source_name": source_name, "publish_date": date_str}
    entities = None
    if ai_analysis:
        article_data.update({"summary": ai_analysis.get("summary"), "category": ai_analysis.get("category"), "severity": ai_analysis.get("severity", "Low"), "source_indicator": 'ai'})
        entities = {'Threat Actor': ai_analysis.get("threat_actors", []), 'Malware': ai_analysis.get("malware", []), 'Vulnerability': ai_analysis.get("vulnerabilities", [])}
        processing_stats['ai_success'] += 1
    else:
        article_data.update({"summary": f"{title.strip()} - {description.strip()}", "category": "Unknown", "severity": "Unknown", "source_indicator": 'fallback'})
        processing_stats['fallback_summary'] += 1
    if is_retry: update_article_in_db(article_data, entities)
    else: add_article_to_db(article_data, entities)

def get_google_alert_digests(service, days=2):
    """Fetches all Google Alert and Daily Digest emails from the last N days."""
    try:
        query = f'from:googlealerts-noreply@google.com subject:("Google Alert" OR "Daily digest") newer_than:{days}d'
        response = service.users().messages().list(userId='me', q=query).execute()
        messages = response.get('messages', [])
        email_bodies = []
        if not messages: return email_bodies
        for msg in messages:
            full_message = service.users().messages().get(userId='me', id=msg['id'], format='raw').execute()
            email_bodies.append(base64.urlsafe_b64decode(full_message['raw'].encode('ASCII')))
        return email_bodies
    except HttpError as error:
        handle_http_error(error)
        return []

def parse_and_process_digests(email_bytes_list, verbose=False):
    """Loops through digest emails and parses them using the reliable JSON markup method."""
    if not email_bytes_list: return
    
    for i, email_bytes in enumerate(email_bytes_list):
        msg = email.message_from_bytes(email_bytes, policy=policy.default)
        subject = msg['Subject']
        print(f"  > Processing Digest {i+1}/{len(email_bytes_list)}: '{subject}'...")
        
        email_date = email.utils.parsedate_to_datetime(msg['Date'])
        html_payload = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html_payload = part.get_payload(decode=True).decode(part.get_content_charset(), 'ignore')
                    break
        if not html_payload: continue
        soup = BeautifulSoup(html_payload, 'lxml')
        
        # This is the reliable method: find the hidden JSON data block.
        json_script_tag = soup.find('script', {'data-scope': 'inboxmarkup'})
        if json_script_tag:
            try:
                # Load the clean JSON data from the script tag
                widgets = json.loads(json_script_tag.string).get('cards', [{}])[0].get('widgets', [])
                for item in tqdm(widgets, desc=f"    Parsing articles", unit="article", leave=False):
                    if item.get('type') == 'LINK':
                        title = item.get('title', 'No Title')
                        actual_url = get_actual_url(item.get('url', '#'))
                        description = item.get('description', 'No Snippet')
                        process_article("Google Alert", title, actual_url, description, email_date, verbose=verbose)
            except Exception as e:
                if verbose: print(f"    > Could not process JSON data from digest. Error: {e}")
        else:
            if verbose: print("    > No 'inboxmarkup' JSON data found in this email.")

def process_rss_feed(name, url, verbose=False):
    try:
        feed = feedparser.parse(url)
        for entry in tqdm(feed.entries[:10], desc=f"Processing RSS '{name}'", unit="article", leave=False):
            title = entry.title
            link = entry.link
            publish_date = email.utils.parsedate_to_datetime(entry.published) if 'published' in entry else datetime.now()
            description = BeautifulSoup(entry.summary, 'lxml').get_text(strip=True, separator=' ')[:200]
            process_article(f"RSS: {name}", title, link, description, publish_date, verbose=verbose)
    except Exception as e:
        if verbose: print(f"  > Error processing RSS feed {name}: {e}")

def retry_fallback_summaries(verbose=False):
    print("\n--- Starting Re-Processing Mode for Fallback Summaries ---")
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT url, source_name, summary, publish_date FROM articles WHERE source_indicator = 'fallback'")
    fallbacks = cursor.fetchall()
    conn.close()
    if not fallbacks:
        print("  > No articles with fallback summaries found to re-process.")
        return
    print(f"  > Found {len(fallbacks)} articles to re-process.")
    for url, source_name, summary, publish_date_str in tqdm(fallbacks, desc="Re-processing fallbacks", unit="article"):
        title = summary.split(' - ')[0] if ' - ' in summary else ''
        description = summary.split(' - ')[1] if ' - ' in summary else ''
        default_date = datetime.fromisoformat(publish_date_str) if publish_date_str else datetime.now()
        process_article(source_name, title, url, description, default_date, is_retry=True, verbose=verbose)

def get_actual_url(google_url):
    try:
        return parse_qs(urlparse(google_url).query)['url'][0]
    except (KeyError, IndexError):
        return google_url

def main():
    load_dotenv()
    start_time = time.time()
    setup_database()
    
    verbose = '--verbose' in sys.argv
    retry_mode = '--retry-fallbacks' in sys.argv

    if retry_mode:
        retry_fallback_summaries(verbose=verbose)
    else:
        print("\n-> Fetching Google Alerts...")
        service = get_gmail_service()
        if service:
            email_bytes_list = get_google_alert_digests(service)
            if email_bytes_list:
                parse_and_process_digests(email_bytes_list, verbose=verbose)
            else:
                print("  > No new Google Alert digest emails found in the last 2 days.")
        
        print("\n-> Fetching RSS Feeds...")
        for name, url in RSS_FEEDS.items():
            process_rss_feed(name, url, verbose=verbose)

    print("\n" + "="*20 + " PROCESSING SUMMARY " + "="*20)
    print(f"  Total Articles Scanned:      {processing_stats['total_processed']}")
    print(f"  Successful AI Summaries:     {processing_stats['ai_success']}")
    print(f"  Fallback Summaries Used:     {processing_stats['fallback_summary']}")
    print(f"  Skipped (Already in DB):     {processing_stats['skipped_duplicate']}")
    print("="*62 + "\n")
    print("-> Data collection complete. Run report_generator.py and visualize_graph.py next.")
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"\n--- Script finished in {elapsed_time:.2f} seconds ---")

if __name__ == '__main__':
    main()
