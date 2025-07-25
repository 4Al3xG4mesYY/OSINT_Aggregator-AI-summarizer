#!/usr/bin/env python
# osint_aggregator.py (Project Synapse)

# This script is a multi-source OSINT aggregator with an advanced scraping engine
# and a data re-processing workflow. It fetches intelligence, scrapes content,
# generates AI summaries, and stores results in a database. It also integrates
# with Slack to avoid duplicating work already covered by a human team.
#
# Dependencies:
# python -m pip install -r requirements.txt
#
# How to Use:
# 1. Make the script executable: chmod +x osint_aggregator.py
# 2. Normal Run: ./osint_aggregator.py "Ransomware" "Malware"
# 3. Full Retry Run: ./osint_aggregator.py --retry-fallbacks
# 4. Targeted Retry Run: ./osint_aggregator.py --retry-fallbacks "RSS: The Hacker News"

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
from curl_cffi import requests as curl_requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# --- CONFIGURATION ---

RSS_FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "Bleeping Computer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "Dark Reading": "https://www.darkreading.com/rss_simple.asp",
    "Wired - Security": "https://www.wired.com/feed/category/security/latest/rss",
    "CSO Online": "https://www.csoonline.com/feed/",
    "SecurityWeek": "http://feeds.feedburner.com/Securityweek",
    "CISA Alerts": "https://www.cisa.gov/news-events/alerts/rss",
    "Malwarebytes Labs": "https://www.malwarebytes.com/blog/feed"
}

SLACK_CONFIG = {
    "enabled": False,
    "bot_token": "xoxb-YOUR-SLACK-BOT-TOKEN-HERE",
    "channel_id": "YOUR-SLACK-CHANNEL-ID-HERE"
}

DB_FILE = "osint_database.db"
RETRY_CONFIG = {"max_retries": 3, "initial_delay": 5}

# --- DATABASE SETUP ---

def setup_database():
    """Creates/updates the database and table if they don't exist."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            source_name TEXT NOT NULL,
            post_content TEXT NOT NULL,
            source_indicator TEXT NOT NULL,
            main_topic TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute("PRAGMA table_info(articles)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'main_topic' not in columns:
        cursor.execute("ALTER TABLE articles ADD COLUMN main_topic TEXT")
        print("Database schema updated with 'main_topic' column.")

    conn.commit()
    conn.close()

def is_url_in_db(url):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM articles WHERE url = ?", (url,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_post_to_db(source_name, post_content, url, source_indicator, main_topic):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO articles (source_name, post_content, url, source_indicator, main_topic) VALUES (?, ?, ?, ?, ?)",
            (source_name, post_content, url, source_indicator, main_topic)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"  > Note: URL {url} was already in DB (IntegrityError).")
    finally:
        conn.close()

def update_post_in_db(url, new_post_content, new_source_indicator, new_main_topic):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE articles SET post_content = ?, source_indicator = ?, main_topic = ? WHERE url = ?",
        (new_post_content, new_source_indicator, new_main_topic, url)
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

def summarize_and_categorize_with_gemini(text):
    """Uses Gemini AI to generate a summary and categorize the article."""
    if not text or len(text.strip()) < 50:
        print("    > Article text too short, skipping AI analysis.")
        return None, None
    api_key = "YOUR_GEMINI_API_KEY_HERE" # Replace with your key
    if "YOUR_GEMINI_API_KEY_HERE" in api_key:
        print("\nERROR: Gemini API key not found.")
        return None, None

    categories = ["Malware Analysis", "Vulnerability Disclosure", "Threat Actor Profile", "Data Breach Report", "Geopolitical Cyber Event", "General Cyber News"]
    prompt = f"""Analyze the following article. First, provide a two-sentence summary for a social media post. Second, classify the article into one of the following categories: {', '.join(categories)}.
    
    Provide your response as a valid JSON object with two keys: "summary" and "category".
    
    Article:
    ---
    {text}
    """
    for attempt in range(RETRY_CONFIG["max_retries"]):
        try:
            print("    > Waiting to respect API rate limit...")
            time.sleep(4)
            print(f"    > Analyzing with AI (Attempt {attempt + 1})...")
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
            response = requests.post(api_url, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get('candidates'):
                    content = result['candidates'][0]['content']['parts'][0]['text']
                    clean_content = content.strip().replace('```json', '').replace('```', '')
                    data = json.loads(clean_content)
                    return data.get('summary'), data.get('category')
                else: return None, None
            elif response.status_code in [503, 408, 500, 502, 504]:
                 time.sleep(RETRY_CONFIG["initial_delay"] * (2 ** attempt))
                 continue
            else: return None, None
        except Exception as e:
            print(f"    > An error occurred during AI analysis: {e}")
            if attempt < RETRY_CONFIG["max_retries"] - 1:
                 time.sleep(RETRY_CONFIG["initial_delay"] * (2 ** attempt))
            else: return None, None
    return None, None

def scrape_article_details(url):
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
    print(f"  > Scraping with Selenium (Headless Chrome): {url}")
    text, publish_date = None, None
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
        text, publish_date = article.text, article.publish_date
        print("    > Selenium scrape successful.")
    except Exception as e:
        print(f"    > Selenium scraping failed: {e}")
    finally:
        if driver:
            driver.quit()
    return text, publish_date

def process_article(source_name, title, url, description, default_date, slack_cache, is_retry=False):
    if not is_retry and is_url_in_db(url):
        print(f"  > Skipping duplicate article: {url}")
        return 'skipped'

    if url in slack_cache:
        print(f"  > Article already covered in Slack: {url}")
        slack_summary, slack_date = slack_cache[url]
        hashtags, emojis = generate_tags_and_emojis(slack_summary)
        post_content = (
            f"CATEGORY: Human Verified\n"
            f"Published: {slack_date.strftime('%A, %B %d, %Y')}\n"
            f"{slack_summary} [VERIFIED BY SLACK]{''.join(emojis)}\n"
            f"{' '.join(hashtags)}\n"
            f"{url}\n"
        )
        if is_url_in_db(url):
             update_post_in_db(url, post_content, 'slack', 'Human Verified')
        else:
             add_post_to_db(source_name, post_content, url, 'slack', 'Human Verified')
        return 'slack'

    print(f"\nProcessing article from '{source_name}': {title}")
    
    if is_retry:
        article_text, publish_date = scrape_with_selenium(url)
    else:
        article_text, publish_date = scrape_article_details(url)

    summary, category = summarize_and_categorize_with_gemini(article_text)
    source_indicator = 'ai' if summary else 'fallback'

    if not summary:
        print("    > Fallback: using summary from source.")
        summary = create_summary(title, description)
        category = "Unknown"

    display_date = publish_date if publish_date else default_date
    
    hashtags, emojis = generate_tags_and_emojis(summary)
    post_content = (
        f"CATEGORY: {category}\n"
        f"Published: {display_date.strftime('%A, %B %d, %Y')}\n"
        f"{summary}{''.join(emojis)}\n"
        f"{' '.join(hashtags)}\n"
        f"{url}\n"
    )

    if is_retry:
        update_post_in_db(url, post_content, source_indicator, category)
    else:
        add_post_to_db(source_name, post_content, url, source_indicator, category)
    
    return source_indicator

def parse_google_alert(keyword, email_bytes, slack_cache):
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
    json_script_tag = soup.find('script', {'data-scope': 'inboxmarkup'})
    
    stats = {'added': 0, 'skipped': 0, 'failed': 0}
    
    if json_script_tag:
        try:
            widgets = json.loads(json_script_tag.string).get('cards', [{}])[0].get('widgets', [])
            for item in widgets:
                if item.get('type') == 'LINK':
                    title = item.get('title', 'No Title')
                    actual_url = get_actual_url(item.get('url', '#'))
                    description = item.get('description', 'No Snippet')
                    result = process_article(source_name, title, actual_url, description, email_date, slack_cache)
                    if result in ['ai', 'slack']: stats['added'] += 1
                    elif result == 'skipped': stats['skipped'] += 1
                    else: stats['failed'] += 1
        except Exception as e:
            print(f"  > Could not process JSON data from Google Alert '{keyword}'. Error: {e}")
    
    print(f"--- Summary for '{source_name}' ---")
    print(f"  New Articles Added: {stats['added']}")
    print(f"  Duplicates Skipped: {stats['skipped']}")
    print(f"  Processing Failed:  {stats['failed']}")
    print("-----------------------------------")


def process_rss_feed(name, url, slack_cache):
    print(f"\n-> Fetching RSS Feed: {name}")
    stats = {'added': 0, 'skipped': 0, 'failed': 0}
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            title = entry.title
            link = entry.link
            publish_date = email.utils.parsedate_to_datetime(entry.published) if 'published' in entry else datetime.now()
            description = BeautifulSoup(entry.summary, 'lxml').get_text(strip=True, separator=' ')[:200]
            result = process_article(f"RSS: {name}", title, link, description, publish_date, slack_cache)
            if result in ['ai', 'slack']: stats['added'] += 1
            elif result == 'skipped': stats['skipped'] += 1
            else: stats['failed'] += 1
            
    except Exception as e:
        print(f"  > An error occurred while processing RSS feed {name}: {e}")
    
    print(f"--- Summary for 'RSS: {name}' ---")
    print(f"  New Articles Added: {stats['added']}")
    print(f"  Duplicates Skipped: {stats['skipped']}")
    print(f"  Processing Failed:  {stats['failed']}")
    print("-----------------------------------")

def retry_fallback_summaries(slack_cache, source_to_retry=None):
    print("\n--- Starting Re-Processing Mode for Fallback Summaries ---")
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    
    query = "SELECT url, source_name, post_content FROM articles WHERE source_indicator = 'fallback'"
    params = []
    if source_to_retry:
        query += " AND source_name = ?"
        params.append(source_to_retry)
        print(f"  > Targeting source: {source_to_retry}")

    cursor.execute(query, params)
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
        date_str, summary_line = lines[1], lines[2] 
        title = summary_line.split(' - ')[0]
        description = ' '.join(summary_line.split(' - ')[1:])
        default_date = datetime.strptime(date_str.replace("Published: ", ""), "%A, %B %d, %Y")
        result = process_article(source_name, title, url, description, default_date, slack_cache, is_retry=True)
        if result == 'ai':
            successful_heals += 1
            
    print("\n--- Re-Processing Summary ---")
    print(f"  Articles Attempted: {total_to_retry}")
    print(f"  Successfully Healed: {successful_heals}")
    print(f"  Failed to Heal:     {total_to_retry - successful_heals}")
    print("-----------------------------")

def fetch_slack_articles(token, channel_id):
    print("\n-> Fetching articles already covered in Slack...")
    if not token or "YOUR-SLACK-BOT-TOKEN-HERE" in token:
        print("  > Slack integration disabled. Token not configured.")
        return {}
    
    client = WebClient(token=token)
    slack_cache = {}
    url_pattern = re.compile(r'<(http[s]?://[^|]+)\|[^>]*>')

    try:
        result = client.conversations_history(channel=channel_id, limit=100)
        for message in result["messages"]:
            text = message.get("text", "")
            match = url_pattern.search(text)
            if match:
                url = match.group(1)
                summary = text.split('<')[0].strip()
                ts = datetime.fromtimestamp(float(message.get("ts", 0)))
                slack_cache[url] = (summary, ts)
        print(f"  > Found {len(slack_cache)} URLs in Slack channel.")
        return slack_cache
    except SlackApiError as e:
        print(f"  > Error fetching from Slack: {e.response['error']}")
        return {}

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
    print("\n-> Generating final report from database...")
    conn = sqlite3.connect(DB_FILE, timeout=10)
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

    slack_cache = {}
    if SLACK_CONFIG["enabled"]:
        slack_cache = fetch_slack_articles(SLACK_CONFIG["bot_token"], SLACK_CONFIG["channel_id"])

    # --- New Argument Parsing Logic ---
    if len(sys.argv) > 1:
        if sys.argv[1] == '--retry-fallbacks':
            source_to_retry = sys.argv[2] if len(sys.argv) > 2 else None
            retry_fallback_summaries(slack_cache, source_to_retry)
        else:
            # This is a normal run
            alert_keywords = sys.argv[1:]
            service = get_gmail_service()
            if service:
                for keyword in alert_keywords:
                    email_bytes = get_latest_google_alert(service, keyword)
                    if email_bytes:
                        parse_google_alert(keyword, email_bytes, slack_cache)
            for name, url in RSS_FEEDS.items():
                process_rss_feed(name, url, slack_cache)
    else:
        print("\nUsage:")
        print("  Normal Run: ./osint_aggregator.py \"<keyword1>\" ...")
        print("  Retry Run (all):  ./osint_aggregator.py --retry-fallbacks")
        print("  Retry Run (targeted): ./osint_aggregator.py --retry-fallbacks \"<source_name>\"")
        sys.exit(1)

    generate_report()
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"\n--- Script finished in {elapsed_time:.2f} seconds ---")

if __name__ == '__main__':
    main()
