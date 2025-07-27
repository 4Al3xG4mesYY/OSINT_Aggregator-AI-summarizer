# app.py
# This is an advanced version of the Flask web application that displays
# the contents of your OSINT database with categorization, different views,
# search functionality, and pagination.

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
ARTICLES_PER_PAGE = 25 # New setting for pagination

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """
    Main route to display a "Daily Briefing" of articles added in the last 24 hours,
    grouped by their main topic.
    """
    conn = get_db_connection()
    time_threshold = datetime.now() - timedelta(hours=24)
    query = "SELECT * FROM articles WHERE created_at >= ? ORDER BY main_topic, created_at DESC"
    recent_articles = conn.execute(query, (time_threshold,)).fetchall()
    conn.close()

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
    New route to display the full archive of all articles with search and pagination.
    """
    conn = get_db_connection()
    
    # Get search query and current page from URL parameters
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ARTICLES_PER_PAGE

    base_query = "FROM articles"
    count_query = "SELECT COUNT(*) "
    select_query = "SELECT * "
    params = []

    # Add search functionality
    if search_query:
        base_query += " WHERE post_content LIKE ?"
        params.append(f'%{search_query}%')

    # Get total number of articles for pagination
    total_articles = conn.execute(count_query + base_query, params).fetchone()[0]
    total_pages = (total_articles + ARTICLES_PER_PAGE - 1) // ARTICLES_PER_PAGE

    # Get the articles for the current page
    paginated_query = select_query + base_query + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([ARTICLES_PER_PAGE, offset])
    articles_for_page = conn.execute(paginated_query, params).fetchall()
    
    conn.close()
    
    return render_template('archive.html', 
                           articles=articles_for_page, 
                           page=page, 
                           total_pages=total_pages, 
                           search_query=search_query)


if __name__ == '__main__':
    app.run(debug=True)
