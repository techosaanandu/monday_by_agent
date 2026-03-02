import streamlit as st
import requests
import json
import os
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage

# -----------------------------
# 1️⃣ LOAD ENV VARIABLES
# -----------------------------
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
DEALS_BOARD_ID = os.getenv("DEALS_BOARD_ID")
WORK_ORDERS_BOARD_ID = os.getenv("WORK_ORDERS_BOARD_ID")

# -----------------------------
# 2️⃣ MONDAY TOOL (LIVE + CLEAN)
# -----------------------------
@tool
def query_monday_boards(board_type: str) -> str:
    """
    Fetch live data from Monday.com.
    Use 'deals' or 'work_orders'.
    """

    board_id = DEALS_BOARD_ID if board_type == "deals" else WORK_ORDERS_BOARD_ID
    url = "https://api.monday.com/v2"

    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }

    query = f"""
    query {{
      boards (ids: [{board_id}]) {{
        items_page (limit: 100) {{
          items {{
            name
            column_values {{
              id
              text
            }}
          }}
        }}
      }}
    }}
    """

    with st.status(f"🔄 Fetching {board_type} data...", expanded=False):

        response = requests.post(
            url,
            json={"query": query},
            headers=headers
        ).json()

        # Safe error handling
        if "errors" in response:
            return "Error fetching data from Monday API."

        raw_items = response["data"]["boards"][0]["items_page"]["items"]

        cleaned_rows = []

        for item in raw_items:
            row = {"Name": item["name"]}

            for col in item["column_values"]:
                val = col["text"]

                if val and any(sym in val for sym in ["$", "₹", ","]):
                    val = val.replace("$", "").replace("₹", "").replace(",", "").strip()

                row[col["id"]] = val if val else "MISSING"

            cleaned_rows.append(row)

        st.success(f"✅ Retrieved {len(cleaned_rows)} rows")

        return json.dumps(cleaned_rows)

# -----------------------------
# 3️⃣ AGENT SETUP
# -----------------------------

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    api_key=GEMINI_API_KEY,
    temperature=0
)

tools = [query_monday_boards]

system_prompt = """
You are a Founder's BI Agent.

Rules:
1. ALWAYS use query_monday_boards to fetch live data.
2. If any value is "MISSING", mention it clearly as a data quality issue.
3. Provide financial insights, not just raw numbers.
4. Ask clarifying questions if the request is ambiguous.
"""

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=system_prompt
)

# -----------------------------
# 4️⃣ STREAMLIT UI
# -----------------------------

st.set_page_config(page_title="Monday BI Agent", layout="centered")
st.title("📊 Monday.com Founder Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat Input
if user_input := st.chat_input("Ask about revenue, sectors, or pipeline..."):

    # Show user message
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):

        # Convert history into LangChain messages
        lc_messages = []

        for msg in st.session_state.messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            else:
                lc_messages.append(AIMessage(content=msg["content"]))

        # Invoke agent correctly
        result = agent.invoke({
            "messages": lc_messages
        })

        output = result["messages"][-1].content

        st.markdown(output)

        st.session_state.messages.append({
            "role": "assistant",
            "content": output
        })