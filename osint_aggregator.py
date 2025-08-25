#!/usr/bin/env python
# osint_aggregator.py (Project Synapse)
#
# This is the unified, feature-rich OSINT aggregator. It is compatible
# with both report_generator.py and visualize_graph.py. It builds a
# graph database, extracts entities, and includes a retry mode.

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

# --- DATABASE SETUP ---

def setup_database():
    """Creates a hybrid database schema compatible with both reporting and visualization."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    # Main articles table with all necessary columns for other scripts
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
    # Entities table for the graph structure
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            UNIQUE(name, type)
        )
    ''')
    # Relationships table for the graph structure
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
        pass # Relationship already exists
    finally:
        conn.close()

def add_article_to_db(article_data, entities=None):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    article_id = None
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

# --- NLTK, SCOPES, and other setup functions ---
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

def get_latest_google_alert(service, keyword):
    try:
        query = f'from:googlealerts-noreply@google.com subject:"Google Alert - {keyword}"'
        response = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = response.get('messages', [])
        if not messages:
            return None
        msg_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=msg_id, format='raw').execute()
        return base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
    except HttpError as error:
        print(f'  > Error fetching email for "{keyword}": {error}')
        return None

@retry(
    retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError)),
    stop=stop_after_attempt(RETRY_CONFIG["max_retries"]),
    wait=wait_fixed(RETRY_CONFIG["initial_delay"])
)
def analyze_article_with_gemini(text):
    if not text or len(text.strip()) < 100:
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("\nERROR: GEMINI_API_KEY not set in .env file.")

    categories = ["Malware Analysis", "Vulnerability Disclosure", "Threat Actor Profile", "Data Breach Report", "Geopolitical Cyber Event", "General Cyber News"]
    prompt = f"""Act as a Cyber Threat Intelligence Analyst. Analyze the following article.
    Provide your response as a single, valid JSON object with the following keys:
    - "summary": A two-sentence summary for a social media post.
    - "category": Classify the article into ONE of the following: {', '.join(categories)}.
    - "severity": Classify the threat's priority for a SOC analyst as "High", "Medium", or "Low". A "High" severity indicates an active exploit, zero-day, or major data breach.
    - "threat_actors": An array of any threat actor groups mentioned (e.g., ["APT28", "Lazarus Group"]). If none, provide an empty array [].
    - "malware": An array of any malware families mentioned (e.g., ["Ryuk", "Emotet"]). If none, provide an empty array [].
    - "vulnerabilities": An array of any CVE identifiers mentioned (e.g., ["CVE-2025-12345"]). If none, provide an empty array [].

    Article:
    ---
    {text}
    """
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}",
            json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        if result.get('candidates'):
            content = result['candidates'][0]['content']['parts'][0]['text']
            clean_content = content.strip().replace('```json', '').replace('```', '')
            return json.loads(clean_content)
        return None
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        raise

def scrape_article_details(url):
    try:
        response = curl_requests.get(url, impersonate="chrome110", timeout=60)
        response.raise_for_status()
        article = Article(url)
        article.set_html(response.content)
        article.parse()
        if not article.text or len(article.text.strip()) < 100:
            raise ArticleException("Content too short or empty")
        return article.text, article.publish_date
    except Exception as e:
        raise

def scrape_with_selenium(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(5)
        article = Article(url)
        article.set_html(driver.page_source)
        article.parse()
        if not article.text or len(article.text.strip()) < 100:
            raise ArticleException("Content too short or empty")
        return article.text, article.publish_date
    except Exception as e:
        raise
    finally:
        if driver:
            driver.quit()

def process_article(source_name, title, url, description, default_date, is_retry=False):
    processing_stats['total_processed'] += 1

    if not is_retry and is_url_in_db(url):
        processing_stats['skipped_duplicate'] += 1
        return

    article_text, publish_date = None, None
    try:
        if is_retry:
            article_text, publish_date = scrape_with_selenium(url)
        else:
            article_text, publish_date = scrape_article_details(url)
    except Exception:
        article_text = f"{title} - {description}"

    ai_analysis = None
    try:
        ai_analysis = analyze_article_with_gemini(article_text)
    except Exception:
        pass

    article_data = {
        "url": url, "title": title, "source_name": source_name,
        "publish_date": publish_date if publish_date else default_date
    }
    entities = None

    if ai_analysis:
        article_data.update({
            "summary": ai_analysis.get("summary"),
            "category": ai_analysis.get("category"),
            "severity": ai_analysis.get("severity", "Low"),
            "source_indicator": 'ai'
        })
        entities = {
            'Threat Actor': ai_analysis.get("threat_actors", []),
            'Malware': ai_analysis.get("malware", []),
            'Vulnerability': ai_analysis.get("vulnerabilities", [])
        }
        processing_stats['ai_success'] += 1
    else:
        article_data.update({
            "summary": f"{title.strip()} - {description.strip()}",
            "category": "Unknown", "severity": "Unknown", "source_indicator": 'fallback'
        })
        processing_stats['fallback_summary'] += 1
    
    if is_retry:
        update_article_in_db(article_data, entities)
    else:
        add_article_to_db(article_data, entities)

def parse_google_alert(keyword, email_bytes):
    if not email_bytes: return
    msg = email.message_from_bytes(email_bytes, policy=policy.default)
    email_date = email.utils.parsedate_to_datetime(msg['Date'])
    source_name = f"Google Alert: {keyword}"
    html_payload = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_payload = part.get_payload(decode=True).decode(part.get_content_charset(), 'ignore')
                break
    if not html_payload: return
    soup = BeautifulSoup(html_payload, 'lxml')
    links = soup.find_all('a')
    for link in tqdm(links, desc=f"Processing Google Alert '{keyword}'", unit="article", leave=False):
        title_tag = link.find('div', style=lambda v: 'font-size:16px' in v if v else False)
        snippet_tag = link.find('div', style=lambda v: 'color:#5f6368' in v if v else False)
        if title_tag and snippet_tag and link.get('href'):
            title = title_tag.get_text(strip=True)
            actual_url = get_actual_url(link['href'])
            description = snippet_tag.get_text(strip=True)
            process_article(source_name, title, actual_url, description, email_date)

def process_rss_feed(name, url):
    try:
        feed = feedparser.parse(url)
        for entry in tqdm(feed.entries[:10], desc=f"Processing RSS '{name}'", unit="article", leave=False):
            title = entry.title
            link = entry.link
            publish_date = email.utils.parsedate_to_datetime(entry.published) if 'published' in entry else datetime.now()
            description = BeautifulSoup(entry.summary, 'lxml').get_text(strip=True, separator=' ')[:200]
            process_article(f"RSS: {name}", title, link, description, publish_date)
    except Exception as e:
        print(f"  > Error processing RSS feed {name}: {e}")

def retry_fallback_summaries():
    print("\n--- Starting Re-Processing Mode for Fallback Summaries ---")
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT url, source_name, title, summary, publish_date FROM articles WHERE source_indicator = 'fallback'")
    fallbacks = cursor.fetchall()
    conn.close()
    if not fallbacks:
        print("  > No articles with fallback summaries found to re-process.")
        return
    
    print(f"  > Found {len(fallbacks)} articles to re-process.")
    for url, source_name, title, summary, publish_date in tqdm(fallbacks, desc="Re-processing fallbacks", unit="article"):
        description = summary.split(' - ')[1] if ' - ' in summary else ''
        default_date = datetime.fromisoformat(publish_date)
        process_article(source_name, title, url, description, default_date, is_retry=True)

def get_actual_url(google_url):
    try:
        return parse_qs(urlparse(google_url).query)['url'][0]
    except (KeyError, IndexError):
        return google_url

def main():
    load_dotenv()
    start_time = time.time()
    setup_database()

    if len(sys.argv) > 1 and sys.argv[1] == '--retry-fallbacks':
        retry_fallback_summaries()
    elif len(sys.argv) > 1:
        alert_keywords = sys.argv[1:]
        print("\n-> Fetching Google Alerts...")
        service = get_gmail_service()
        if service:
            for keyword in alert_keywords:
                email_bytes = get_latest_google_alert(service, keyword)
                if email_bytes:
                    parse_google_alert(keyword, email_bytes)
                else:
                    print(f"  > No Google Alert emails found for '{keyword}'")
        
        print("\n-> Fetching RSS Feeds...")
        for name, url in RSS_FEEDS.items():
            process_rss_feed(name, url)
    else:
        print("\nUsage:")
        print("  Normal Run: python osint_aggregator.py \"<keyword1>\" ...")
        print("  Retry Run:  python osint_aggregator.py --retry-fallbacks")
        sys.exit(1)

    print("\n" + "="*20 + " PROCESSING SUMMARY " + "="*20)
    print(f"  Total Articles Scanned:      {processing_stats['total_processed']}")
    print(f"  Successful AI Summaries:     {processing_stats['ai_success']}")
    print(f"  Fallback Summaries Used:     {processing_stats['fallback_summary']}")
    print(f"  Skipped (Already in DB):     {processing_stats['skipped_duplicate']}")
    print("="*62 + "\n")
    print("-> Data collection complete. Run the other scripts to generate reports and visualizations.")
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"\n--- Script finished in {elapsed_time:.2f} seconds ---")

if __name__ == '__main__':
    main()
