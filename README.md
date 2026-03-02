# Monday.com Business Intelligence Agent

A conversational AI agent that answers founder-level business questions using **live** data from monday.com boards (Deals & Work Orders).

## Features implemented
- Live monday.com API v2 integration (no caching, no preloading)
- Natural language query understanding with follow-up support
- Automatic tool calling to fetch fresh board data when needed
- Visible API call traces (GraphQL queries + responses shown in expanders)
- Basic data cleaning & resilience handling (missing values marked, simple format normalization)
- Graceful error handling & user-friendly messages
- Hosted on Streamlit Community Cloud (zero setup for evaluator)

## Live demo
🔗 https://mondaybyagent-almcawzbp2ebmur4wyydp5.streamlit.app/
(just paste your monday.com API token + Groq API key in the sidebar)

## How to run locally
```bash
# 1. Clone or unzip the project
# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
streamlit run app.py
# or if your main file has different name: streamlit run grok.py
