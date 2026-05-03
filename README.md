# Multimodal Recipe Assistant

A multimodal RAG assistant designed to answer culinary questions, suggest meal ideas, and provide detailed step-by-step cooking instructions.

## Architecture & Pipeline

### Data Source & Scraping (`scripts/scrape-swiggy-recipes.py`)

- Using asynchronous Playwright, the scraper mimics human interaction to handle React-based UI elements, including infinite scrolling, modals, and lazy-loaded overlays.
- Beyond simple parsing, it uses targeted Regex to isolate specific metadata (Prep Time, Calories, Servings) and performs automated deduplication of instructions and ingredients.
- To handle large-scale data collection, the script implements a checkpoint-and-retry system, allowing the process to resume seamlessly if interrupted.

### Embeddings & Vector Store (`scripts/build-rag.py`)

- OpenCLIP `ViT-B-32` is utilized to encode both recipe descriptions and high-resolution images. This allows the system to understand that a photo of a biryani and the word "biryani" belong in the same conceptual neighborhood.
- These embeddings are indexed using ChromaDB backed by SQLite. This setup enables high-performance similarity searches without requiring an external cloud database.
- Recipe data is transformed into LangChain `Document` objects, allowing the LLM to "read" the relevant scraped data before answering a user query.

### Chat & Web App (`app/app.py`)

- Using Ollama, the system dynamically toggles between llama3.2 (for fast text responses) and llama3.2-vision (when the user provides an image as input).
- At boot, the system offloads the heavy initialization of the CLIP model and Vector DB to a background daemon thread. This prevents the Flask server from locking up, allowing the web UI to be interactive instantly.
- To protect system RAM, the backend is configured to prevent model duplication, ensuring the ~4GB ViT model only occupies a single instance in memory.

## Prerequisites

- Python 3.9+
- Ollama installed and running locally
- Pull required Ollama models:
  ```bash
  ollama pull llama3.2
  ollama pull llama3.2-vision
  ```

## Instructions To Run

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Scrape Data

If you are starting from a blank slate, you'll need to fetch the recipes first.  
NOTE: Playwright requires browsers to be installed.

```bash
playwright install chromium
python scripts/scrape-swiggy-recipes.py
```

### Run the Web App

Launch the Flask backend and wait for the "warm-up complete" log in the terminal indicating Chroma is ready.

```bash
python app/app.py
```

### Open in Browser

Visit `http://127.0.0.1:8000` to interact with the assistant!

You can upload pictures of ingredients or dishes, or type in queries like:

- What can I make with paneer and spinach in 20 minutes?
- I'm craving something sweet today.
- Suggest me a meal under 500 kcal.
