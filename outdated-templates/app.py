# app.py
# This is an advanced version of the Flask web application that displays
# the contents of your OSINT database with categorization and different views.

# --- Dependencies ---
# In your activated virtual environment, run:
# pip install Flask

# --- How to Run ---
# 1. Make sure your `osint_database.db` file is in the same folder.
# 2. Create a 'templates' folder and place 'index.html' and 'archive.html' inside it.
# 3. Run this script from your terminal: python app.py
# 4. Open your web browser and go to: http://127.0.0.1:5000

import sqlite3
from flask import Flask, render_template, request
from datetime import datetime, timedelta

app = Flask(__name__)

DB_FILE = "osint_database.db"

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # This allows accessing columns by name
    return conn

@app.route('/')
def index():
    """
    Main route to display a "Daily Briefing" of articles added in the last 24 hours,
    grouped by their main topic.
    """
    conn = get_db_connection()
    
    # Calculate the timestamp for 24 hours ago
    time_threshold = datetime.now() - timedelta(hours=24)
    
    # Query for recent articles
    query = """
        SELECT * FROM articles 
        WHERE created_at >= ? 
        ORDER BY main_topic, created_at DESC
    """
    recent_articles = conn.execute(query, (time_threshold,)).fetchall()
    conn.close()

    # Group articles by category in Python
    articles_by_category = {}
    for article in recent_articles:
        category = article['main_topic'] if article['main_topic'] else "Unknown"
        if category not in articles_by_category:
            articles_by_category[category] = []
        articles_by_category[category].append(article)

    return render_template('index.html', articles_by_category=articles_by_category)

@app.route('/archive')
def archive():
    """
    New route to display the full archive of all articles, grouped by category.
    """
    conn = get_db_connection()
    
    # Query all articles, ordered for grouping
    all_articles = conn.execute('SELECT * FROM articles ORDER BY main_topic, created_at DESC').fetchall()
    conn.close()
    
    # Group articles by category in Python
    articles_by_category = {}
    for article in all_articles:
        category = article['main_topic'] if article['main_topic'] else "Unknown"
        if category not in articles_by_category:
            articles_by_category[category] = []
        articles_by_category[category].append(article)
    
    return render_template('archive.html', articles_by_category=articles_by_category)


if __name__ == '__main__':
    app.run(debug=True)
