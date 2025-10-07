import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio   # ✅ Added for Kaleido fix
from fpdf import FPDF
from langchain.chat_models import init_chat_model
import json
import tempfile
import base64
import os
import unicodedata  # ✅ For cleaning text

# ✅ --- Use Streamlit Secrets instead of .env ---
groq_api_key = st.secrets["GROQ_API_KEY"]

# ✅ Initialize model with your API key
model = init_chat_model(
    "llama-3.1-8b-instant",
    model_provider="groq",
    api_key=groq_api_key
)

# ---- Load dataset ----
df = pd.read_csv("ODI_Match_info.csv")

# ---- Streamlit Page Config ----
st.set_page_config(page_title="ODI Match Report", page_icon="🏏", layout="centered")

# ---- Custom CSS ----
st.markdown(
    """
    <style>
    .main { background-color: #f8fafc; }
    .report-card {
        background-color: white;
        padding: 2.0rem 2rem;
        border-radius: 14px;
        box-shadow: 0px 6px 20px rgba(16,24,40,0.06);
        width: 82%;
        margin: auto;
    }
    .stTextInput > div > div > input {
        border: 1px solid #e6e9ef;
        border-radius: 10px;
        padding: 14px;
        font-size: 16px;
    }
    .stButton > button {
        width: 100%;
        border-radius: 10px;
        height: 3rem;
        font-size: 1.05rem;
        font-weight: 700;
        background-color: #0d6efd;
        color: white;
        border: none;
        transition: all 0.12s ease-in-out;
    }
    .stButton > button:hover { background-color: #084298; transform: translateY(-1px); }
    h1 { text-align: center; color: #0d6efd; font-weight: 800; margin-bottom: 0.3rem; }
    .subtext { text-align: center; font-size: 1rem; color: #6c757d; margin-bottom: 1.6rem; }
    iframe { border-radius: 12px; border: 2px solid #eee; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- Helper: Clean text for PDF ----
def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

# ---- UI Layout ----
st.markdown("<div class='report-card'>", unsafe_allow_html=True)
st.markdown("<h1>🏏 ODI Cricket Match Report Generator</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtext'>Type a natural language query. The app will build a chart and pack it into a PDF report.</p>", unsafe_allow_html=True)

query = st.text_input("💬 Enter your query (e.g. *Show total toss wins by team in a pie chart*)")
generate = st.button("🚀 Generate Report")

st.markdown("</div>", unsafe_allow_html=True)

# ---- Helper: safe JSON parsing ----
def parse_model_json(raw):
    try:
        return json.loads(raw.strip())
    except Exception:
        try:
            return json.loads(raw.split("```json")[1].split("```")[0])
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start:end+1])
                except Exception:
                    return None
            return None

# ✅ Example code to include in PDF
code_example = """
import pandas as pd
import plotly.express as px

df = pd.read_csv('ODI_Match_info.csv')
data = df['player_of_match'].value_counts().reset_index()
data.columns = ['player_of_match', 'count']
fig = px.bar(data, x='player_of_match', y='count', title='Most Common Player of the Match')
fig.show()
"""

if generate and query:
    # ---- Step 1: Ask model for chart spec ----
    prompt = f"""
    You are a data visualization assistant.
    Dataset columns: ['team1', 'team2', 'toss_winner', 'winner', 'player_of_match', 'season'].

    Based on this query: "{query}", return ONLY valid JSON (no explanation, no code).
    JSON must have keys: x, y, chart_type, and optional limit.

    Example:
    {{
      "x": "toss_winner",
      "y": "count",
      "chart_type": "pie"
    }}
    """
    response = model.invoke(input=prompt)
    chart_info = parse_model_json(response.content if hasattr(response, "content") else str(response))

    if not chart_info:
        st.error("⚠️ Model output is not valid JSON. Please try rephrasing the query.")
        st.stop()

    x = chart_info.get("x")
    y = chart_info.get("y")
    chart_type = chart_info.get("chart_type")
    limit = chart_info.get("limit", None)

    if not x or not y or not chart_type:
        st.error("⚠️ Model JSON must include x, y, and chart_type.")
        st.stop()

    if x not in df.columns:
        st.error(f"⚠️ Column '{x}' not found in dataset. Available: {list(df.columns)}")
        st.stop()

    # ---- Step 2: Prepare data ----
    if y == "count":
        data = df[x].value_counts().reset_index()
        data.columns = [x, "count"]
        if limit:
            data = data.head(limit)
        value_col = "count"
    else:
        if y not in df.columns:
            st.error(f"⚠️ Column '{y}' not found in dataset. If you intended to count, set y to 'count'.")
            st.stop()
        if pd.api.types.is_numeric_dtype(df[y]):
            data = df.groupby(x)[y].sum().reset_index()
            value_col = y
            if limit:
                data = data.sort_values(by=value_col, ascending=False).head(limit)
        else:
            data = df[x].value_counts().reset_index()
            data.columns = [x, "count"]
            value_col = "count"
            if limit:
                data = data.head(limit)

    # ---- Step 3: Build Plotly figure ----
    try:
        if chart_type.lower() == "pie":
            fig = px.pie(
                data, names=x, values=value_col, title=query,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
        else:
            fig = px.bar(
                data, x=x, y=value_col, title=query,
                color=x if value_col == "count" else None,
                color_discrete_sequence=px.colors.qualitative.Set3, text_auto=True
            )
    except Exception as e:
        st.error(f"Error creating chart: {e}")
        st.stop()

    # ✅ ---- Step 4: Save chart image (fixed Kaleido issue) ----
    try:
        pio.kaleido.scope.default_format = "png"
        pio.kaleido.scope.chromium_args = ()  # ✅ No Chrome dependency

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            fig.write_image(tmpfile.name, scale=2)
            chart_path = tmpfile.name
    except Exception as e:
        st.error(f"Error saving chart image. ({e})")
        st.stop()

    # ---- Step 5: Generate PDF ----
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "ODI Cricket Match Report", ln=True, align="C")

    pdf.set_font("Arial", size=12)
    pdf.ln(4)
    pdf.multi_cell(0, 8, f"Query: {clean_text(query)}")

    pdf.ln(2)
    pdf.set_font("Courier", size=10)
    pdf.multi_cell(0, 7, "JSON Output:\n" + clean_text(json.dumps(chart_info, indent=2)))

    pdf.ln(4)
    pdf.image(chart_path, x=30, w=150)

    pdf.ln(8)
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 8, "Equivalent Python Code:")

    pdf.set_font("Courier", size=8)
    for line in clean_text(code_example).splitlines():
        pdf.multi_cell(0, 5, line)

    pdf_output = pdf.output(dest="S").encode("latin1", "ignore")

    # ---- Step 6: Show PDF ----
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📄 PDF Preview")
    base64_pdf = base64.b64encode(pdf_output).decode("utf-8")
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="700" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

    st.download_button(
        label="📥 Download PDF Report",
        data=pdf_output,
        file_name="ODI_Match_Report.pdf",
        mime="application/pdf"
    )

    try:
        os.remove(chart_path)
    except Exception:
        pass
