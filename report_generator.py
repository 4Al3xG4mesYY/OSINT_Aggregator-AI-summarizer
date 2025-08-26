#!/usr/bin/env python
# report_generator.py
#
# This script connects to the SQLite database populated by osint_aggregator.py
# and generates a professional HTML report and a machine-readable JSON file.
# It is intended for educational and defensive cybersecurity purposes for
# the Cyber News Live nonprofit.

import sqlite3
import json
import os
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader

# --- CONFIGURATION ---
DB_FILE = "osint_database.db"
HTML_TEMPLATE_FILE = "report_template.html"
HTML_OUTPUT_FILE = "Weekly_Threat_Report.html"
JSON_OUTPUT_FILE = "Weekly_Threat_Report.json"
DAYS_TO_REPORT = 7 # Report on articles from the last 7 days

def get_articles_from_db():
    """Fetches recent articles from the database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    cursor = conn.cursor()
    
    date_threshold = datetime.now() - timedelta(days=DAYS_TO_REPORT)
    
    cursor.execute(
        """SELECT * FROM articles
           WHERE publish_date >= ?
           ORDER BY
             CASE severity
               WHEN 'High' THEN 1
               WHEN 'Medium' THEN 2
               WHEN 'Low' THEN 3
               ELSE 4
             END,
             publish_date DESC""",
        (date_threshold,)
    )
    articles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return articles

def group_articles_by_severity(articles):
    """Groups articles into High, Medium, Low, and Unknown categories."""
    grouped_articles = {
        'High': [],
        'Medium': [],
        'Low': [],
        'Unknown': []
    }
    for article in articles:
        severity = article.get('severity', 'Unknown')
        if severity in grouped_articles:
            grouped_articles[severity].append(article)
        else:
            grouped_articles['Unknown'].append(article)
    return grouped_articles

def create_html_report(grouped_articles):
    """Generates an HTML report from a Jinja2 template."""
    if not os.path.exists(HTML_TEMPLATE_FILE):
        with open(HTML_TEMPLATE_FILE, "w", encoding='utf-8') as f:
            f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weekly Threat Report</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f4f9; color: #333; }
        .container { max-width: 800px; margin: 20px auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1, h2 { color: #1a237e; }
        h1 { text-align: center; border-bottom: 2px solid #3949ab; padding-bottom: 10px; margin-top: 0; }
        .severity-high { border-left: 5px solid #d32f2f; }
        .severity-medium { border-left: 5px solid #fbc02d; }
        .severity-low { border-left: 5px solid #388e3c; }
        .severity-unknown { border-left: 5px solid #757575; }
        .article { background: #f9f9f9; margin-bottom: 15px; padding: 15px; border-radius: 5px; }
        .article h3 { margin-top: 0; font-size: 1.1em; }
        .article-meta { font-size: 0.8em; color: #555; margin-bottom: 10px; }
        .article-summary { margin-bottom: 10px; line-height: 1.6; }
        .article-tags { font-size: 0.9em; color: #3949ab; }
        .article-tags span { margin-right: 5px; }
        a { color: #3949ab; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Weekly Threat Report</h1>
        <p style="text-align:center; color: #666;">Report Generated: {{ generation_date }}</p>
        
        {% for severity, articles in articles_by_severity.items() %}
            {% if articles %}
                <h2>{{ severity }} Severity Threats</h2>
                {% for article in articles %}
                    <div class="article severity-{{ severity.lower() }}">
                        <h3><a href="{{ article.url }}" target="_blank">{{ article.title }}</a></h3>
                        <div class="article-meta">
                            <strong>Source:</strong> {{ article.source_name }} | 
                            <strong>Published:</strong> {{ article.publish_date | format_date }} |
                            <strong>Category:</strong> {{ article.category }}
                        </div>
                        <p class="article-summary">{{ article.summary }}</p>
                        <div class="article-tags">
                            <span>{{ article.summary | generate_tags('emojis') | join(' ') }}</span>
                            <span>{{ article.summary | generate_tags('hashtags') | join(' ') }}</span>
                        </div>
                    </div>
                {% endfor %}
            {% endif %}
        {% endfor %}
    </div>
</body>
</html>
            """)

    env = Environment(loader=FileSystemLoader('.'))
    
    def format_date(timestamp_str):
        if not timestamp_str: return "N/A"
        try:
            dt_obj = datetime.fromisoformat(timestamp_str)
            return dt_obj.strftime('%A, %B %d, %Y')
        except (ValueError, TypeError):
            return "Invalid Date"
    
    def generate_tags(text, tag_type):
        text_lower = text.lower() if text else ""
        hashtags = {"#Cybersecurity"}
        emojis = []
        keyword_map = {
            'ransomware': ('#Ransomware', '💰'), 'healthcare': ('#Healthcare', '🏥'),
            'attack': ('#CyberAttack', '💥'), 'breach': ('#DataBreach', '🔒'),
            'vulnerability': ('#Vulnerability', '⚠️'), 'hacker': ('#Hacking', '💻'),
            'ai': ('#AI', '🤖'), 'android': ('#Android', '🤖'), 'ios': ('#iOS', '📱'),
            'microsoft': ('#Microsoft', '💻'), 'critical infrastructure': ('#CriticalInfrastructure', '🏭'),
            'phishing': ('#Phishing', '🎣'), 'malware': ('#Malware', '🪲')
        }
        for keyword, (tag, emoji) in keyword_map.items():
            if keyword in text_lower:
                hashtags.add(tag)
                if emoji not in emojis:
                    emojis.append(emoji)
        if not emojis:
            emojis.extend(['🚨', '🛡️'])
        
        if tag_type == 'hashtags':
            return list(hashtags)
        elif tag_type == 'emojis':
            return emojis
        return []

    env.filters['format_date'] = format_date
    env.filters['generate_tags'] = generate_tags
    
    template = env.get_template(HTML_TEMPLATE_FILE)
    
    html_output = template.render(
        articles_by_severity=grouped_articles,
        generation_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
    
    with open(HTML_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_output)
    print(f"-> Successfully generated HTML report: {HTML_OUTPUT_FILE}")

def create_json_report(articles):
    # This function remains unchanged
    for article in articles:
        for key, value in article.items():
            if isinstance(value, datetime):
                article[key] = value.isoformat()
    report_data = {
        "report_generated_at": datetime.now().isoformat(),
        "report_period_days": DAYS_TO_REPORT,
        "article_count": len(articles),
        "articles": articles
    }
    with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=4)
    print(f"-> Successfully generated JSON report: {JSON_OUTPUT_FILE}")

def main():
    print("\n--- Generating Threat Intelligence Report ---")
    if not os.path.exists(DB_FILE):
        print(f"ERROR: Database file '{DB_FILE}' not found.")
        print("Please run osint_aggregator.py first to collect data.")
        return

    articles = get_articles_from_db()
    
    if not articles:
        print("-> No recent articles found in the database to report on.")
        return
        
    print(f"-> Found {len(articles)} articles from the last {DAYS_TO_REPORT} days.")
    
    grouped_articles = group_articles_by_severity(articles)
    
    create_html_report(grouped_articles)
    create_json_report(articles)
    
    print("\n--- Report generation complete. ---")

if __name__ == '__main__':
    main()
