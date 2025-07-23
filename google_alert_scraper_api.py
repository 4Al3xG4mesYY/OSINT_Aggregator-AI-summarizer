#!/usr/bin/env python
# google_alert_scraper_api.py (Advanced Version)

# This script is a multi-source OSINT aggregator with an advanced scraping engine
# and a data re-processing workflow. It fetches intelligence, scrapes content,
# generates AI summaries, and stores results in a database.
#
# Dependencies:
# Run this command in your activated venv to install all packages:
# python -m pip install -r requirements.txt
#
# How to Use:
# 1. Make the script executable (one-time setup):
#    chmod +x google_alert_scraper_api.py
#
# 2. Normal Run (collect new articles):
#    ./google_alert_scraper_api.py "Ransomware" "Malware"
#
# 3. Re-processing Run (retry failed scrapes with Selenium):
#    ./google_alert_scraper_api.py --retry-fallbacks

import base64
import email
import json
import os.path
import sys
import time
from email import policy
from urllib.parse import parse_qs, urlparse
from datetime import datetime
import random
import sqlite3

import requests
import feedparser
import nltk
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from newspaper import Article
from curl_cffi import requests as curl_requests # For impersonating browsers
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options

# --- CONFIGURATION ---

RSS_FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "Bleeping Computer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "Dark Reading": "https://www.darkreading.com/rss_simple.asp",
}

RETRY_CONFIG = {
    "max_retries": 3,
    "initial_delay": 5
}

DB_FILE = "osint_database.db"

# --- DATABASE SETUP ---

def setup_database():
    """Creates/updates the database and table if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            source_name TEXT NOT NULL,
            post_content TEXT NOT NULL,
            summary_type TEXT NOT NULL, -- 'ai' or 'fallback'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute("PRAGMA table_info(articles)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'summary_type' not in columns:
        cursor.execute("ALTER TABLE articles ADD COLUMN summary_type TEXT NOT NULL DEFAULT 'fallback'")
        print("Database schema updated with 'summary_type' column.")

    conn.commit()
    conn.close()

def is_url_in_db(url):
    """Checks if a URL has already been processed and stored."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM articles WHERE url = ?", (url,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_post_to_db(source_name, post_content, url, summary_type):
    """Adds a new processed article to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO articles (source_name, post_content, url, summary_type) VALUES (?, ?, ?, ?)",
            (source_name, post_content, url, summary_type)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"  > Note: URL {url} was already in DB (IntegrityError).")
    finally:
        conn.close()

def update_post_in_db(url, new_post_content, new_summary_type):
    """Updates an existing article in the database, typically after a successful re-scrape."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE articles SET post_content = ?, summary_type = ? WHERE url = ?",
        (new_post_content, new_summary_type, url)
    )
    conn.commit()
    conn.close()
    print(f"  > Successfully updated article in database: {url}")


# --- NLTK SETUP ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    print("NLTK 'punkt' package not found. Downloading...")
    nltk.download('punkt')
    print("'punkt' package downloaded successfully.")

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# --- CORE FUNCTIONS ---

def get_gmail_service():
    """Handles Gmail API authentication."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("\nERROR: `credentials.json` not found.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_console()
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        return build('gmail', 'v1', credentials=creds)
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

def get_latest_google_alert(service, keyword):
    """Fetches the most recent Google Alert email."""
    print(f"\n-> Fetching Google Alert for: '{keyword}'...")
    try:
        query = f'from:googlealerts-noreply@google.com subject:"Google Alert - {keyword}"'
        response = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = response.get('messages', [])

        if not messages:
            print(f"  > No Google Alert emails found for the keyword: '{keyword}'")
            return None

        msg_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=msg_id, format='raw').execute()
        return base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
    except HttpError as error:
        print(f'  > An error occurred while fetching the email for "{keyword}": {error}')
        return None

def summarize_with_gemini(text):
    """Uses the Gemini API to generate a two-sentence summary, with rate limiting and retries."""
    if not text or len(text.strip()) < 50:
        print("    > Article text too short, skipping AI summary.")
        return None

    api_key = "YOUR_GEMINI_API_KEY_HERE"
    if "YOUR_GEMINI_API_KEY_HERE" in api_key:
        print("\nERROR: Gemini API key not found.")
        return None

    prompt = f"Summarize the following article in exactly two sentences for a social media post:\n\n---\n\n{text}"
    
    for attempt in range(RETRY_CONFIG["max_retries"]):
        try:
            print("    > Waiting to respect API rate limit...")
            time.sleep(4)
            
            print(f"    > Summarizing with AI (Attempt {attempt + 1})...")
            chat_history = [{"role": "user", "parts": [{"text": prompt}]}]
            payload = {"contents": chat_history}
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
            
            response = requests.post(api_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('candidates'):
                    return result['candidates'][0]['content']['parts'][0]['text'].strip()
                else:
                    print(f"    > AI summary generation failed. API response: {result}")
                    return None
            
            elif response.status_code in [503, 408, 500, 502, 504]:
                 print(f"    > AI summary failed with server error {response.status_code}. Retrying...")
                 time.sleep(RETRY_CONFIG["initial_delay"] * (2 ** attempt))
                 continue
            else:
                print(f"    > AI summary generation failed with status {response.status_code}: {response.text}")
                return None
        
        except requests.exceptions.RequestException as e:
            print(f"    > An error occurred during AI summarization: {e}")
            if attempt < RETRY_CONFIG["max_retries"] - 1:
                 time.sleep(RETRY_CONFIG["initial_delay"] * (2 ** attempt))
            else:
                print("    > All AI summary attempts failed.")
                return None
    return None


def scrape_article_details(url):
    """Scrapes an article URL using curl_cffi to bypass anti-scraping."""
    print(f"  > Scraping article with advanced client: {url}")
    try:
        response = curl_requests.get(url, impersonate="chrome110", timeout=15)
        response.raise_for_status()

        article = Article(url)
        article.set_html(response.content)
        article.parse()
        
        return article.text, article.publish_date
    except Exception as e:
        print(f"    > Advanced scraping failed: {e}")
        return None, None

def scrape_with_selenium(url):
    """Scrapes a URL using Selenium for JavaScript-heavy sites."""
    print(f"  > Scraping with Selenium (Headless Chrome): {url}")
    text = None
    publish_date = None
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(5)
        
        article = Article(url)
        article.set_html(driver.page_source)
        article.parse()
        
        text = article.text
        publish_date = article.publish_date
        print("    > Selenium scrape successful.")

    except Exception as e:
        print(f"    > Selenium scraping failed: {e}")
    finally:
        if driver:
            driver.quit()
            
    return text, publish_date


def process_article(source_name, title, url, description, default_date, is_retry=False):
    """Shared logic to process a single article from any source."""
    if not is_retry and is_url_in_db(url):
        print(f"  > Skipping duplicate article: {url}")
        return 'skipped'

    print(f"\nProcessing article from '{source_name}': {title}")
    
    if is_retry:
        article_text, publish_date = scrape_with_selenium(url)
    else:
        article_text, publish_date = scrape_article_details(url)

    summary = summarize_with_gemini(article_text)
    summary_type = 'ai' if summary else 'fallback'

    if not summary:
        print("    > Fallback: using summary from source.")
        summary = create_summary(title, description)

    display_date = publish_date if publish_date else default_date
    formatted_date = display_date.strftime("%A, %B %d, %Y")

    hashtags, emojis = generate_tags_and_emojis(summary)
    
    post_content = (
        f"{formatted_date}\n"
        f"{summary}{''.join(emojis)}\n"
        f"{' '.join(hashtags)}\n"
        f"{url}\n"
    )

    if is_retry:
        update_post_in_db(url, post_content, summary_type)
    else:
        add_post_to_db(source_name, post_content, url, summary_type)
    
    return summary_type

def parse_google_alert(keyword, email_bytes):
    """Parses a Google Alert email and processes its articles."""
    if not email_bytes:
        return
        
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
    json_script_tag = soup.find('script', {'data-scope': 'inboxmarkup'})
    if json_script_tag:
        try:
            json_data = json.loads(json_script_tag.string)
            widgets = json_data.get('cards', [{}])[0].get('widgets', [])
            
            for item in widgets:
                if item.get('type') == 'LINK':
                    title = item.get('title', 'No Title')
                    google_url = item.get('url', '#')
                    actual_url = get_actual_url(google_url)
                    description = item.get('description', 'No Snippet')
                    process_article(source_name, title, actual_url, description, email_date)
        except Exception as e:
            print(f"  > Could not process JSON data from Google Alert '{keyword}'. Error: {e}")

def process_rss_feed(name, url):
    """Fetches and processes articles from an RSS feed."""
    print(f"\n-> Fetching RSS Feed: {name}")
    try:
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:5]:
            title = entry.title
            link = entry.link
            publish_date = email.utils.parsedate_to_datetime(entry.published) if 'published' in entry else datetime.now()
            description = BeautifulSoup(entry.summary, 'lxml').get_text(strip=True, separator=' ')[:200]
            
            process_article(f"RSS: {name}", title, link, description, publish_date)
            
    except Exception as e:
        print(f"  > An error occurred while processing RSS feed {name}: {e}")

def retry_fallback_summaries():
    """Queries DB for fallback summaries and attempts to re-process them with Selenium."""
    print("\n--- Starting Re-Processing Mode for Fallback Summaries ---")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT url, source_name, post_content FROM articles WHERE summary_type = 'fallback'")
    fallbacks = cursor.fetchall()
    conn.close()

    if not fallbacks:
        print("  > No articles with fallback summaries found to re-process.")
        return

    total_to_retry = len(fallbacks)
    successful_heals = 0
    print(f"  > Found {total_to_retry} articles to re-process.")
    
    for url, source_name, post_content in fallbacks:
        lines = post_content.split('\n')
        date_str = lines[0]
        summary_line = lines[1]
        title = summary_line.split(' - ')[0]
        description = ' '.join(summary_line.split(' - ')[1:])
        default_date = datetime.strptime(date_str, "%A, %B %d, %Y")

        result = process_article(source_name, title, url, description, default_date, is_retry=True)
        if result == 'ai':
            successful_heals += 1
    
    print("\n--- Re-Processing Summary ---")
    print(f"  Articles Attempted: {total_to_retry}")
    print(f"  Successfully Healed: {successful_heals}")
    print(f"  Failed to Heal:     {total_to_retry - successful_heals}")
    print("-----------------------------")


# --- Helper functions ---

def get_actual_url(google_url):
    try:
        return parse_qs(urlparse(google_url).query)['url'][0]
    except (KeyError, IndexError):
        return google_url

def generate_tags_and_emojis(text):
    text_lower = text.lower()
    hashtags = {"#Cybersecurity"}
    emojis = []
    keyword_map = {
        'ransomware': ('#Ransomware', '💰'), 'healthcare': ('#Healthcare', '🏥'),
        'attack': ('#CyberAttack', '💥'), 'breach': ('#DataBreach', '🔒'),
        'vulnerability': ('#Vulnerability', '⚠️'), 'hacker': ('#Hacking', '💻'),
        'ai': ('#AI', '🤖'), 'android': ('#Android', '🤖'), 'ios': ('#iOS', '📱'),
        'microsoft': ('#Microsoft', '💻'), 'critical infrastructure': ('#CriticalInfrastructure', '🏭'),
        'phishing': ('#Phishing', '🎣'), 'malware': ('#Malware', '👾')
    }
    for keyword, (tag, emoji) in keyword_map.items():
        if keyword in text_lower:
            hashtags.add(tag)
            if emoji not in emojis:
                emojis.append(emoji)
    if not emojis:
        emojis.extend(['🚨', '🛡️'])
    return list(hashtags), emojis

def create_summary(title, snippet):
    return f"{title.strip()} - {snippet.strip()}".replace("...", "")

def generate_report():
    """Reads all articles from the database and generates the final text report."""
    print("\n-> Generating final report from database...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT source_name, post_content FROM articles ORDER BY source_name, id DESC")
    all_posts = cursor.fetchall()
    conn.close()

    if all_posts:
        output_file = "scraped_alerts.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            current_source = ""
            for source_name, post_content in all_posts:
                if source_name != current_source:
                    f.write(f"\n{'='*15} {source_name.upper()} {'='*15}\n\n")
                    current_source = source_name
                
                f.write(post_content)
                f.write("\n" + "-"*40 + "\n\n")
        
        print(f"\nSuccessfully generated report with {len(all_posts)} total articles.")
        print(f"Report saved to '{output_file}'")
    else:
        print("\nNo new articles were found to generate a report.")

def main():
    start_time = time.time()
    setup_database()

    if len(sys.argv) > 1 and sys.argv[1] == '--retry-fallbacks':
        retry_fallback_summaries()
    elif len(sys.argv) > 1:
        alert_keywords = sys.argv[1:]
        
        print("Connecting to Gmail API...")
        service = get_gmail_service()
        
        if service:
            for keyword in alert_keywords:
                email_bytes = get_latest_google_alert(service, keyword)
                if email_bytes:
                    parse_google_alert(keyword, email_bytes)

        for name, url in RSS_FEEDS.items():
            process_rss_feed(name, url)
    else:
        print("\nUsage:")
        print("  Normal Run: ./google_alert_scraper_api.py \"<keyword1>\" \"<keyword2>\" ...")
        print("  Retry Run:  ./google_alert_scraper_api.py --retry-fallbacks")
        sys.exit(1)

    generate_report()

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"\n--- Script finished in {elapsed_time:.2f} seconds ---")


if __name__ == '__main__':
    main()
