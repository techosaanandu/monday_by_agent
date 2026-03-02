import streamlit as st
import requests
import json
from openai import OpenAI

st.set_page_config(page_title="Monday BI Agent", layout="wide")
st.title("Monday.com BI Agent – Founder Level")
st.caption("Live API • Groq + llama-3.1-8b-instant • No caching")


with st.sidebar:
    st.header("Credentials")
    monday_token = st.text_input("monday.com API v2 token", type="password")
    groq_key     = st.text_input("Groq API key", type="password")

    st.header("Board IDs")
    deals_id     = st.text_input("Deals board ID", value="5026936381")
    orders_id    = st.text_input("Work Orders board ID", value="5026936307")

# ── Helper: monday.com GraphQL ──────────────────────────
def monday_graphql(query: str):
    if not monday_token: return None, "Missing token"
    try:
        r = requests.post(
            "https://api.monday.com/v2",
            headers={"Authorization": monday_token, "Content-Type": "application/json"},
            json={"query": query}
        )
        data = r.json()
        if "errors" in data:
            return None, str(data["errors"])
        return data, None
    except Exception as e:
        return None, str(e)

# ── Tool: fetch board (with visible trace) ──────────────
def fetch_board(board_id: str, board_name: str):
    query = f"""
    query {{
      boards(ids:[{board_id}]) {{
        name
        columns {{ id title }}
        items_page(limit:200) {{
          items {{
            id name
            column_values {{ id text }}
          }}
        }}
      }}
    }}
    """

    with st.expander(f"API call → {board_name}", expanded=False):
        st.code(query, "graphql")
        data, err = monday_graphql(query)
        if err:
            st.error(err)
            return None
        st.json(data, expanded=False)
    return data

# ── Chat ────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("Ask anything about deals / work orders …"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not monday_token or not groq_key:
            st.error("Fill both tokens in sidebar first")
            st.stop()

        client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")

        system = f"""You are a monday.com BI agent.
Boards:
- Deals       ID = {deals_id}
- Work Orders ID = {orders_id}

Rules:
- ALWAYS use the tool to get fresh data
- Data is messy → handle missing values, typos, different formats
- Show numbers + short insight + data quality notes
- Ask clarifying questions when needed
- Be concise and founder-friendly"""

        messages = [{"role": "system", "content": system}] + st.session_state.messages

        tools = [{
            "type": "function",
            "function": {
                "name": "fetch_board",
                "description": "Fetch current items from one monday.com board",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string"},
                        "board_name": {"type": "string"}
                    },
                    "required": ["board_id", "board_name"]
                }
            }
        }]

        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",   # or llama-3.3-70b-versatile if you have higher tier
            messages=messages,
            tools=tools,
            temperature=0.15,
            max_tokens=1200
        )

        msg = resp.choices[0].message

        if not msg.tool_calls:
            answer = msg.content
        else:
            # very simple tool handling (one step)
            tc = msg.tool_calls[0]
            args = json.loads(tc.function.arguments)
            data = fetch_board(args["board_id"], args["board_name"])

            if not data:
                answer = "Could not fetch data from monday.com."
            else:
                # feed back to LLM
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": json.dumps(data, indent=2)[:20000] + "\n... (truncated if very large)"
                }

                resp2 = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=messages + [msg, tool_msg]
                )
                answer = resp2.choices[0].message.content

        st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})