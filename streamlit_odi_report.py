import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import plotly.io as pio
import os
import tempfile
import base64

# --- ✅ Fix Kaleido + Chrome compatibility ---
try:
    from plotly.io._kaleido import scope
    scope.chromium_args = ["--no-sandbox", "--disable-dev-shm-usage"]
except Exception as e:
    print("⚠️ Kaleido init skipped:", e)

pio.renderers.default = "kaleido"

# --- Optional fallback path for Streamlit Cloud ---
if os.path.exists("/usr/bin/google-chrome"):
    os.environ["CHROME_PATH"] = "/usr/bin/google-chrome"

# ---- Streamlit App ----
st.set_page_config(page_title="ODI Match Report", page_icon="📊", layout="centered")

st.markdown("<h1 style='text-align: center; color: #003366;'>📊 ODI Match Report Generator</h1>", unsafe_allow_html=True)

# ---- Upload dataset ----
uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.success("✅ File uploaded successfully!")

    # ---- Display Data ----
    st.subheader("📋 Uploaded Data")
    st.dataframe(df.head())

    # ---- Generate Plotly Chart ----
    st.subheader("📈 Run Rate Comparison")
    if 'Team' in df.columns and 'RunRate' in df.columns:
        fig = px.bar(df, x='Team', y='RunRate', color='Team', title="Run Rate per Team",
                     color_discrete_sequence=px.colors.qualitative.Set3)
        st.plotly_chart(fig, use_container_width=True)

        # --- ✅ Save chart image (Fixed Kaleido) ---
        chart_path = os.path.join(tempfile.gettempdir(), "chart.png")
        try:
            fig.write_image(chart_path)
        except Exception as e:
            st.warning(f"⚠️ Error saving chart image: {e}")
            chart_path = None

        # ---- Generate PDF ----
        st.subheader("🧾 Generate PDF Report")

        if st.button("Create PDF Report"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(200, 10, txt="ODI Match Report", ln=True, align='C')
            pdf.ln(10)

            pdf.set_font("Arial", '', 12)
            pdf.cell(0, 10, txt="Team Performance Summary", ln=True)

            if chart_path and os.path.exists(chart_path):
                pdf.image(chart_path, x=25, y=40, w=160)
                pdf.ln(90)

            # Add some data summary
            pdf.set_font("Arial", '', 11)
            summary_text = f"Total Teams: {df['Team'].nunique()} | Average Run Rate: {df['RunRate'].mean():.2f}"
            pdf.cell(0, 10, txt=summary_text, ln=True)

            pdf_output_path = os.path.join(tempfile.gettempdir(), "ODI_Match_Report.pdf")
            pdf.output(pdf_output_path)

            # ---- Display PDF Preview ----
            with open(pdf_output_path, "rb") as f:
                pdf_bytes = f.read()

            b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="700" height="800" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)

            st.success("✅ PDF generated successfully!")

    else:
        st.error("❌ Required columns 'Team' and 'RunRate' not found in dataset.")
else:
    st.info("📂 Please upload your CSV file to generate the report.")
