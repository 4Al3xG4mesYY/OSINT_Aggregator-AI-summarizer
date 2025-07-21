# google_alert_scraper_api.py

# This script is a multi-source OSINT aggregator. It securely connects to your
# Gmail account to fetch Google Alerts and also scrapes RSS feeds. It visits
# each article URL, scrapes the content, uses the Gemini AI to generate a
# two-sentence summary, and formats the output into a clean, organized report.
#
# Dependencies:
# Run this single command in your activated virtual environment to install all packages:
# pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib beautifulsoup4 lxml newspaper3k nltk lxml_html_clean requests feedparser
#
# How to Use:
# 1. Complete the setup for `credentials.json` (Gmail API) and your Gemini API Key.
# 2. PASTE YOUR GEMINI API KEY into the script below.
# 3. (Optional) Add RSS feed URLs to the `RSS_FEEDS` list below.
# 4. Run from your terminal with one or more keywords:
#    python google_alert_scraper_api.py "Ransomware" "ICS Cyber" "Malware"

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
from newspaper import Article, Config

# --- CONFIGURATION ---

RSS_FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "Bleeping Computer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "Dark Reading": "https://www.darkreading.com/rss_simple.asp",
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
]

RETRY_CONFIG = {
    "max_retries": 3,
    "initial_delay": 5
}

DB_FILE = "osint_database.db"

# --- DATABASE SETUP ---

def setup_database():
    """Creates the database and table if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            source_name TEXT NOT NULL,
            post_content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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

def add_post_to_db(source_name, post_content, url):
    """Adds a new processed article to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO articles (source_name, post_content, url) VALUES (?, ?, ?)",
            (source_name, post_content, url)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"  > Note: URL {url} was already in DB (IntegrityError).")
    finally:
        conn.close()

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
    """Uses the Gemini API to generate a two-sentence summary, with rate limiting."""
    print("    > Waiting to respect API rate limit...")
    time.sleep(4)
    
    print("    > Summarizing with AI...")
    if not text or len(text.strip()) < 50:
        print("    > Article text too short, skipping AI summary.")
        return None

    api_key = "YOUR_GEMINI_API_KEY_HERE"

    if "YOUR_GEMINI_API_KEY_HERE" in api_key:
        print("\nERROR: Gemini API key not found.")
        return None

    prompt = f"Summarize the following article in exactly two sentences for a social media post:\n\n---\n\n{text}"
    
    try:
        chat_history = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {"contents": chat_history}
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
        
        response = requests.post(api_url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('candidates'):
                return result['candidates'][0]['content']['parts'][0]['text'].strip()
            else:
                print(f"    > AI summary generation failed. API response: {result}")
                return None
        else:
            print(f"    > AI summary generation failed with status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"    > An error occurred during AI summarization: {e}")
        return None

def scrape_article_details(url):
    """Scrapes an article URL with retries and rotating user-agents."""
    print(f"  > Scraping article: {url}")
    
    for attempt in range(RETRY_CONFIG["max_retries"]):
        try:
            config = Config()
            config.browser_user_agent = random.choice(USER_AGENTS)
            config.request_timeout = 10

            article = Article(url, config=config)
            article.download()
            article.parse()
            
            return article.text, article.publish_date
        
        except Exception as e:
            print(f"    > Attempt {attempt + 1} failed: {e}")
            if attempt < RETRY_CONFIG["max_retries"] - 1:
                delay = RETRY_CONFIG["initial_delay"] * (2 ** attempt)
                print(f"    > Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"    > All {RETRY_CONFIG['max_retries']} attempts failed. Giving up on this article.")
                return None, None
    return None, None

def process_article(source_name, title, url, description, default_date):
    """Shared logic to process a single article from any source."""
    if is_url_in_db(url):
        print(f"  > Skipping duplicate article: {url}")
        return

    print(f"\nProcessing article from '{source_name}': {title}")
    article_text, publish_date = scrape_article_details(url)

    summary = summarize_with_gemini(article_text)
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
    add_post_to_db(source_name, post_content, url)

def parse_google_alert(keyword, email_bytes):
    """Parses a Google Alert email and processes its articles."""
    if not email_bytes:
        return
        
    msg = email.message_from_bytes(email_bytes, policy=policy.default)
    email_date = email.utils.parsedate_to_datetime(msg['Date'])

    html_payload = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_payload = part.get_payload(decode=True).decode(part.get_content_charset(), 'ignore')
                break
    
    if not html_payload:
        return

    soup = BeautifulSoup(html_payload, 'lxml')
    source_name = f"Google Alert: {keyword}"
    
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
    if len(sys.argv) < 2:
        print("\nUsage: python google_alert_scraper_api.py \"<keyword1>\" \"<keyword2>\" ...")
        sys.exit(1)

    start_time = time.time() # Record the start time
    
    setup_database()
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

    generate_report()

    end_time = time.time() # Record the end time
    elapsed_time = end_time - start_time
    print(f"\n--- Script finished in {elapsed_time:.2f} seconds ---")


if __name__ == '__main__':
    main()
