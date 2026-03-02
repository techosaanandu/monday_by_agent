import streamlit as st
import requests
import json
from openai import OpenAI
import pandas as pd

st.set_page_config(page_title="Monday BI Agent", page_icon="📊", layout="wide")
st.title("🧠 Monday.com Business Intelligence Agent")
st.caption("Live monday.com API • Handles messy data • Founder-level insights")
st.info("Groq free tier + llama-3.1-8b-instant • Aggressive filtering & truncation to stay under token limits")

# ────────────────────────────────────────────────
#                SIDEBAR
# ────────────────────────────────────────────────
with st.sidebar:
    st.header("🔑 Credentials")
    monday_token = st.text_input("Monday.com API v2 Token", type="password")
    groq_api_key = st.text_input("Groq API Key", type="password")

    st.header("📋 Board IDs")
    deals_board_id = st.text_input("Deals Board ID", value="5026936381")
    work_board_id = st.text_input("Work Orders Board ID", value="5026936307")

    st.markdown("---")
    st.caption("Current model: llama-3.1-8b-instant (highest TPM on free tier)")

# ────────────────────────────────────────────────
#                monday.com GraphQL
# ────────────────────────────────────────────────
def run_monday_query(query: str) -> dict | None:
    if not monday_token:
        st.error("Monday.com API token missing")
        return None

    try:
        r = requests.post(
            "https://api.monday.com/v2",
            headers={"Authorization": monday_token, "Content-Type": "application/json"},
            json={"query": query}
        )
        data = r.json()
        if "errors" in data:
            st.error(f"monday.com error:\n{json.dumps(data['errors'], indent=2)}")
            return None
        return data
    except Exception as e:
        st.error(f"Request failed: {str(e)}")
        return None


def fetch_board(board_id: str, board_name: str, extra_filter=""):
    # Basic filter support (very limited – real version would parse user intent)
    filter_part = ""
    if extra_filter.strip():
        filter_part = f", query_rules: {extra_filter}"

    query = f"""
    query {{
      boards(ids: [{board_id}]) {{
        name
        columns {{ id title type }}
        items_page(limit: 300 {filter_part}) {{
          items {{
            id name
            column_values {{ id text value }}
          }}
        }}
      }}
    }}
    """

    label = f"{board_name} (id {board_id})"
    if extra_filter:
        label += f" — filtered"

    with st.expander(f"API → {label}", expanded=False):
        st.code(query.strip(), language="graphql")
        result = run_monday_query(query)
        if result:
            st.json(result, expanded=False)
    return result


# ────────────────────────────────────────────────
#                Chat persistence
# ────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ────────────────────────────────────────────────
#                Main loop
# ────────────────────────────────────────────────
if prompt := st.chat_input("Ask e.g. “Pipeline status energy sector this quarter?”"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not monday_token or not groq_api_key:
            st.error("Missing Monday.com token or Groq API key.")
            st.stop()

        client = OpenAI(
            api_key=groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        system = f"""You are a senior BI analyst answering founder-level questions using live monday.com data.

Boards available:
• Deals       ID = {deals_board_id}
• Work Orders ID = {work_board_id}

MANDATORY RULES to stay under token limits:
1. NEVER fetch a full board if it might contain >30–40 items.
2. For ANY question about sectors, revenue, pipeline, dates, status, top deals, this quarter, last month, etc.:
   → FIRST ask the user for concrete filters. Examples:
     • Sector = Energy
     • Status = Closed Won / Won / Lost / In Negotiation
     • Date range = Q1 2026 / after 2025-10-01 / last 90 days
     • Value > 50000
     • Only top 10 deals by value
     • Only items updated this month
3. Only after receiving filter(s) → use fetch_board tool with appropriate rules.
4. Data is intentionally messy → normalize (Energy/energy/enrgy → same), handle missing values, mention data quality issues.
5. Always give concise numbers + insight + caveats.
6. If unclear → ask clarifying question.

Start conservative — ask for filters on broad questions."""

        messages = [{"role": "system", "content": system}] + st.session_state.messages

        tools = [{
            "type": "function",
            "function": {
                "name": "fetch_board",
                "description": "Fetch items from a monday.com board. Use filters whenever possible to keep result small.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "board_id":   {"type": "string"},
                        "board_name": {"type": "string", "description": "Deals or Work Orders"},
                        "filter":     {"type": "string", "description": "GraphQL query_rules object string, e.g. {column_id: {text: {eq: \"Energy\"}}}"}
                    },
                    "required": ["board_id", "board_name"]
                }
            }
        }]

        # ───── First LLM call ─────
        try:
            resp1 = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.15,
                max_tokens=1024
            )
        except Exception as e:
            st.error(f"First LLM call failed:\n{str(e)}")
            st.stop()

        msg = resp1.choices[0].message
        full_answer = msg.content or ""

        # ───── Tool loop ─────
        while msg.tool_calls:
            messages.append(msg)

            for tc in msg.tool_calls:
                if tc.function.name != "fetch_board":
                    continue

                args = json.loads(tc.function.arguments)
                bid = args.get("board_id")
                bname = args.get("board_name", "Unknown")
                filt = args.get("filter", "")

                raw = fetch_board(bid, bname, filt)

                # ───── Make compact output ─────
                try:
                    items = raw["data"]["boards"][0]["items_page"]["items"]
                    if len(items) > 35:
                        # Emergency truncation
                        head = items[:20]
                        summary = f"Total items: {len(items)}\nShowing first 20 + rough stats"
                        rows = [{"id": i["id"], "name": i["name"]} | {cv["id"]: cv.get("text") for cv in i["column_values"]} for i in head]
                    else:
                        rows = [{"id": i["id"], "name": i["name"]} | {cv["id"]: cv.get("text") for cv in i["column_values"]} for i in items]
                        summary = ""

                    df = pd.DataFrame(rows)
                    json_str = df.to_json(orient="records", indent=2)

                    if len(json_str) > 18000:
                        json_str = json_str[:17500] + '\n...\n[truncated – too large for context window]'

                    content = f"**{bname}** (id {bid}) – {len(items)} items total\n```json\n{json_str}\n```"
                    if summary:
                        content = summary + "\n\n" + content

                except Exception:
                    content = json.dumps(raw, indent=2)[:15000] + "\n... [raw fallback – truncated]"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": content
                })

            # ───── Next LLM call ─────
            try:
                resp2 = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.15,
                    max_tokens=1024
                )
            except Exception as e:
                st.error(f"Follow-up LLM call failed:\n{str(e)}")
                st.stop()

            msg = resp2.choices[0].message
            if msg.content:
                full_answer += "\n" + msg.content

            # Safety break (prevent infinite loop)
            if len(messages) > 15:
                full_answer += "\n\n[Stopped – too many tool calls]"
                break

        # ───── Final presentation ─────
        answer = full_answer.strip() or "(No final answer – most likely token limit or unclear question)"
        st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})