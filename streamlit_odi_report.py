import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv
import json
import tempfile
import base64
import os
import unicodedata
import plotly.io as pio

# ---- Load environment variables ----
load_dotenv()

# ---- Fix for Kaleido Deprecation + Chart Color Template ----
pio.kaleido.scope.default_format = "png"
pio.kaleido.scope.default_scale = 2
pio.templates.default = "plotly_white"  # ✅ Ensures visible colors and consistent backgrounds

# ---- Page Configuration ----
st.set_page_config(page_title="🏏 ODI Match Report Generator", page_icon="🏏", layout="centered")

# ---- Load Dataset ----
if os.path.exists("ODI_Match_info.csv"):
    df = pd.read_csv("ODI_Match_info.csv")
else:
    uploaded = st.file_uploader("📂 Upload ODI_Match_info.csv", type=["csv"])
    if uploaded:
        df = pd.read_csv(uploaded)
    else:
        st.warning("Please upload the ODI_Match_info.csv file to continue.")
        st.stop()

# ---- Initialize Model ----
try:
    model = init_chat_model("llama-3.1-8b-instant", model_provider="groq")
except Exception as e:
    st.error(f"⚠️ Failed to initialize model. Check your GROQ_API_KEY. Error: {e}")
    st.stop()

# ---- Styling ----
st.markdown(
    """
    <style>
    .main { background-color: #f8fafc; }
    .report-card {
        background-color: white;
        padding: 2rem 2rem;
        border-radius: 14px;
        box-shadow: 0px 6px 20px rgba(16,24,40,0.06);
        width: 82%;
        margin: auto;
    }
    h1 { text-align: center; color: #0d6efd; font-weight: 800; margin-bottom: 0.3rem; }
    .subtext { text-align: center; font-size: 1rem; color: #6c757d; margin-bottom: 1.6rem; }
    .stTextInput > div > div > input {
        border: 1px solid #e6e9ef; border-radius: 10px; padding: 14px; font-size: 16px;
    }
    .stButton > button {
        width: 100%; border-radius: 10px; height: 3rem; font-size: 1.05rem;
        font-weight: 700; background-color: #0d6efd; color: white; border: none;
        transition: all 0.12s ease-in-out;
    }
    .stButton > button:hover { background-color: #084298; transform: translateY(-1px); }
    iframe { border-radius: 12px; border: 2px solid #eee; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- Helper: Clean text ----
def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

# ---- Helper: Parse JSON ----
def parse_model_json(raw):
    try:
        return json.loads(raw.strip())
    except Exception:
        try:
            return json.loads(raw.split("```json")[1].split("```")[0])
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start:end+1])
                except Exception:
                    return None
            return None

# ---- UI ----
st.markdown("<div class='report-card'>", unsafe_allow_html=True)
st.markdown("<h1>🏏 ODI Cricket Match Report Generator</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtext'>Type a natural language query and generate chart-based PDF insights.</p>", unsafe_allow_html=True)

query = st.text_input("💬 Enter your query (e.g. *Show total toss wins by team in a pie chart*)")
generate = st.button("🚀 Generate Report")

st.markdown("</div>", unsafe_allow_html=True)

# ---- Example Code ----
code_example = """
import pandas as pd
import plotly.express as px

df = pd.read_csv('ODI_Match_info.csv')
data = df['player_of_match'].value_counts().reset_index()
data.columns = ['player_of_match', 'count']
fig = px.bar(data, x='player_of_match', y='count', title='Most Common Player of the Match')
fig.show()
"""

# ---- Main Processing ----
if generate and query:
    prompt = f"""
    You are a data visualization assistant.
    Dataset columns: {list(df.columns)}.
    Based on this query: "{query}", return ONLY valid JSON (no explanation, no code).
    JSON must have keys: x, y, chart_type, and optional limit.

    Example:
    {{
      "x": "toss_winner",
      "y": "count",
      "chart_type": "pie"
    }}
    """

    try:
        response = model.invoke(input=prompt)
        chart_info = parse_model_json(response.content if hasattr(response, "content") else str(response))
    except Exception as e:
        st.error(f"Model request failed: {e}")
        st.stop()

    if not chart_info:
        st.error("⚠️ Model output invalid. Please rephrase your query.")
        st.stop()

    x = chart_info.get("x")
    y = chart_info.get("y")
    chart_type = chart_info.get("chart_type")
    limit = chart_info.get("limit", None)

    # ---- Validate Columns ----
    available_cols = list(df.columns)
    if not x or not y or not chart_type:
        st.error("⚠️ JSON must include x, y, and chart_type.")
        st.stop()

    # 🔹 Auto-correct column names
    if x not in available_cols:
        if "team" in x.lower():
            x = "team1"
        elif "winner" in x.lower():
            x = "winner"
        elif "toss" in x.lower():
            x = "toss_winner"
        else:
            st.error(f"⚠️ Column '{x}' not found. Available columns: {available_cols}")
            st.stop()

    if y != "count" and y not in available_cols:
        y = "count"

    # ---- Prepare Data ----
    if y == "count":
        data = df[x].value_counts().reset_index()
        data.columns = [x, "count"]
        if limit:
            data = data.head(limit)
        value_col = "count"
    else:
        if pd.api.types.is_numeric_dtype(df[y]):
            data = df.groupby(x)[y].sum().reset_index()
            value_col = y
            if limit:
                data = data.sort_values(by=value_col, ascending=False).head(limit)
        else:
            data = df[x].value_counts().reset_index()
            data.columns = [x, "count"]
            value_col = "count"

    # ---- Create Chart ----
    try:
        if chart_type.lower() == "pie":
            fig = px.pie(data, names=x, values=value_col, title=query)
        else:
            fig = px.bar(data, x=x, y=value_col, title=query, text_auto=True)
    except Exception as e:
        st.error(f"Error creating chart: {e}")
        st.stop()

    # ---- Save Chart as Image (Color Fixed) ----
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            fig.update_layout(
                paper_bgcolor="white",
                plot_bgcolor="white",
                font_color="black"
            )
            fig.write_image(tmpfile.name, format="png", scale=2, engine="kaleido")
            chart_path = tmpfile.name
    except Exception as e:
        st.error(f"⚠️ Error saving chart image (Kaleido): {e}")
        st.stop()

    # ---- Generate PDF ----
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

   
    # ---- PDF Preview (Chrome-safe + Instant Load) ----
st.markdown("<br>", unsafe_allow_html=True)
st.subheader("📄 PDF Preview")

# Save PDF to a temporary file
with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
    tmp_pdf.write(pdf_output)
    tmp_pdf_path = tmp_pdf.name

# Embed PDF inside the app
with open(tmp_pdf_path, "rb") as f:
    base64_pdf = base64.b64encode(f.read()).decode("utf-8")

iframe_html = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="700" type="application/pdf"></iframe>'
st.markdown(iframe_html, unsafe_allow_html=True)

# Open PDF in new tab (now works instantly)
pdf_url = f"file://{tmp_pdf_path}"
open_link_html = f'''
    <a href="{pdf_url}" target="_blank" rel="noopener noreferrer"
       style="display:inline-block;margin-top:6px;padding:8px 12px;background:#0d6efd;color:white;border-radius:8px;text-decoration:none;">
        🔍 Open PDF in new tab
    </a>
'''
st.markdown(open_link_html, unsafe_allow_html=True)

# Download button
st.download_button(
    label="📥 Download PDF Report",
    data=pdf_output,
    file_name="ODI_Match_Report.pdf",
    mime="application/pdf",
)

    try:
        os.remove(chart_path)
    except Exception:
        pass
