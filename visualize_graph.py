# visualize_graph.py
import sqlite3
import networkx as nx
from pyvis.network import Network

DB_FILE = "osint_database.db"

# 1. Create a graph object
G = nx.Graph()

# 2. Connect to the database
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 3. Get all entities and add them as nodes to the graph
print("-> Adding entities as nodes...")
cursor.execute("SELECT name, type FROM entities")
entities = cursor.fetchall()
for entity_name, entity_type in entities:
    G.add_node(entity_name, group=entity_type, title=f"Type: {entity_type}")

# 4. Get all articles and add them as nodes
print("-> Adding articles as nodes...")
cursor.execute("SELECT id, title FROM articles")
articles = cursor.fetchall()
for article_id, article_title in articles:
    # --- FIX: Check for a missing title and provide a default value ---
    if not article_title:
        article_title = "Untitled Article"
    # --- END FIX ---

    # We use the ID to ensure the node is unique
    node_id = f"article_{article_id}"
    G.add_node(node_id, group='article', title=article_title, label=f"Article: {article_title[:30]}...")

# 5. Get the relationships and add them as edges (links)
print("-> Adding relationships as edges...")
cursor.execute("""
    SELECT r.article_id, e.name
    FROM relationships r
    JOIN entities e ON r.entity_id = e.id
""")
relationships = cursor.fetchall()
for article_id, entity_name in relationships:
    article_node_id = f"article_{article_id}"
    G.add_edge(article_node_id, entity_name)

conn.close()

# 6. Generate the interactive HTML file using pyvis
print(f"-> Found {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
print("-> Generating interactive graph HTML file...")
nt = Network(notebook=False, height="800px", width="100%", heading="OSINT Threat Intelligence Graph")
nt.from_nx(G)
nt.show_buttons(filter_=['physics'])
nt.save_graph("threat_intelligence_graph.html")

print("\n-> Success! Open 'threat_intelligence_graph.html' in your browser to see the graph.")
