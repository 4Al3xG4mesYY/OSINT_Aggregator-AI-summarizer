# Version 1: Local .eml File Scraper
# This was the initial version of the script. It is designed to parse a
# Google Alert email that has been manually saved as an .eml file.
# It does not use any APIs and is fully self-contained for local use.

import email
from email import policy
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from datetime import datetime

def get_actual_url(google_url):
    """Extracts the actual destination URL from a Google Alert redirect link."""
    try:
        parsed_url = urlparse(google_url)
        return parse_qs(parsed_url.query)['url'][0]
    except (KeyError, IndexError):
        return google_url

def generate_tags_and_emojis(text):
    """Generates relevant hashtags and emojis based on keywords in the text."""
    text_lower = text.lower()
    hashtags = {"#Cybersecurity", "#Ransomware"}
    emojis = []
    keyword_map = {
        'healthcare': ('#Healthcare', '🏥'),
        'attack': ('#CyberAttack', '💥'),
        'breach': ('#DataBreach', '🔒'),
        'vulnerability': ('#Vulnerability', '⚠️'),
        'hacker': ('#Hacking', '💻'),
        'ai': ('#AI', '🤖'),
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
    """Creates a concise, one-sentence summary from the title and snippet."""
    summary = f"{title.strip()} - {snippet.strip()}"
    return summary.replace("...", "")

def parse_google_alert_email(file_path="alert.eml"):
    """
    Parses an .eml file, extracts Google Alert items, and formats them.
    """
    try:
        with open(file_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return []

    date_str = msg['Date']
    email_date = email.utils.parsedate_to_datetime(date_str)
    formatted_date = email_date.strftime("%A, %B %d, %Y")

    html_payload = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_payload = part.get_payload(decode=True).decode(part.get_content_charset(), 'ignore')
                break
    else:
        if msg.get_content_type() == "text/html":
            html_payload = msg.get_payload(decode=True).decode(msg.get_content_charset(), 'ignore')

    if not html_payload:
        return []

    soup = BeautifulSoup(html_payload, 'lxml')
    alert_items = soup.find_all('table', cellpadding="0", cellspacing="0", border="0", width="100%")
    
    formatted_posts = []
    for item in alert_items:
        link_tag = item.find('a', href=True)
        snippet_tag = item.find('font', color='#666666')

        if link_tag and snippet_tag and link_tag.get_text(strip=True):
            title = link_tag.get_text(strip=True)
            google_url = link_tag['href']
            actual_url = get_actual_url(google_url)
            snippet = snippet_tag.get_text(strip=True)

            summary = create_summary(title, snippet)
            hashtags, emojis = generate_tags_and_emojis(summary)

            post = (
                f"{formatted_date}\n"
                f"{summary}{''.join(emojis)}\n"
                f"{' '.join(hashtags)}\n"
                f"{actual_url}\n"
            )
            formatted_posts.append(post)
    return formatted_posts

if __name__ == "__main__":
    email_file = "alert.eml"
    posts = parse_google_alert_email(email_file)
    if posts:
        output_file = "scraped_alerts.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            for post in posts:
                f.write(post)
                f.write("\n" + "="*40 + "\n\n")
        print(f"Successfully scraped {len(posts)} alerts to '{output_file}'")
    else:
        print("No alerts were found or an error occurred.")
