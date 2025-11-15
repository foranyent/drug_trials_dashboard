import streamlit as st
import requests
import pandas as pd
import feedparser
from datetime import datetime
import re

# ============================================================
# Page Setup + Styling
# ============================================================
st.set_page_config(
    page_title="Experimental Drug & Clinical Trial Explorer",
    layout="wide"
)

# Custom Styling
st.markdown("""
<style>

.block-container {
    max-width: 1500px !important;
}

h2, h3 {
    margin-top: 1.2rem;
    margin-bottom: 0.3rem;
}

.dataframe td, .dataframe th {
    white-space: normal !important;
    text-wrap: wrap !important;
}

.stRadio > div > label {
    font-size: 0.9rem !important;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# Helper functions
# ============================================================
def clean_html(text):
    if not text:
        return ""
    clean = re.sub('<.*?>', '', text)
    return clean.strip()


def parse_date(date_str: str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except:
            pass
    return None


# ============================================================
# Fetch trials using API v2
# ============================================================
def fetch_trials(expr: str, max_rnk: int = 100):
    url = "https://clinicaltrials.gov/api/v2/studies"

    params = {
        "format": "json",
        "query.term": expr,
        "pageSize": max_rnk,
    }

    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    rows = []

    for s in data.get("studies", []):
        protocol = s.get("protocolSection", {})

        ident = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        sponsor = protocol.get("sponsorCollaboratorsModule", {})
        conditions = protocol.get("conditionsModule", {})
        design = protocol.get("designModule", {})
        arms = protocol.get("armsInterventionsModule", {})
        locs = protocol.get("contactsLocationsModule", {})

        nct = ident.get("nctId", "")
        title = ident.get("officialTitle") or ident.get("briefTitle") or ""

        interventions = [inv["name"] for inv in arms.get("interventions", []) if "name" in inv]
        condition_list = conditions.get("conditions") or []
        phase_list = design.get("phases") or []

        start_date = status.get("startDateStruct", {}).get("date", "")
        first_post = status.get("studyFirstPostDateStruct", {}).get("date", "")
        last_update = status.get("lastUpdatePostDateStruct", {}).get("date", "")

        sponsor_name = sponsor.get("leadSponsor", {}).get("name", "")

        loc_list = locs.get("locations", []) or []
        city = loc_list[0].get("city", "") if loc_list else ""
        state = loc_list[0].get("state", "") if loc_list else ""
        country = loc_list[0].get("country", "") if loc_list else ""

        rows.append({
            "NCT ID": nct,
            "Title": title,
            "Intervention / Drug": ", ".join(interventions),
            "Condition": ", ".join(condition_list),
            "Phase": ", ".join(phase_list),
            "Status": status.get("overallStatus", ""),
            "Sponsor": sponsor_name,
            "Start Date": start_date,
            "First Posted": first_post,
            "Last Updated": last_update,
            "City": city,
            "State": state,
            "Country": country,
            "CT Link": f"https://clinicaltrials.gov/study/{nct}",
            "_LastUpdated_dt": parse_date(last_update),
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values(by="_LastUpdated_dt", ascending=False)

    return df


# ============================================================
# Fetch Related News Articles
# ============================================================
import urllib.parse

def fetch_articles(drug_term: str, condition_term: str = ""):
    # Build safe search terms
    terms = []

    if drug_term and isinstance(drug_term, str):
        terms.append(drug_term.strip())

    if condition_term and isinstance(condition_term, str):
        terms.append(condition_term.strip())

    # Always anchor with this
    terms.append("clinical trial")

    # Filter empty items
    terms = [t for t in terms if t]

    # If nothing valid left
    if not terms:
        return []

    # SAFE URL encoding
    query = " ".join(terms)
    query_encoded = urllib.parse.quote_plus(query)

    # Streamlit Cloud-safe Google News RSS parameters
    url = (
        "https://news.google.com/rss/search?"
        f"q={query_encoded}"
        "&hl=en-US"        # required for Cloud
        "&gl=US"           # required for Cloud
        "&ceid=US:en"      # forces proper region feed
    )

    # Proper headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
    except Exception as e:
        return []

    articles = []
    for entry in feed.entries[:5]:
        try:
            summary = clean_html(getattr(entry, "summary", ""))[:260]
        except:
            summary = ""

        articles.append({
            "title": entry.title,
            "link": entry.link,
            "published": getattr(entry, "published", ""),
            "summary": summary,
        })

    return articles



# ============================================================
# HEADER (Clean User-Facing)
# ============================================================
st.title("🧪 Experimental Drug & Clinical Trial Explorer")
st.markdown("""
Stay updated on the newest experimental drug trials around the world.  
Search any drug, disease, company, or medical keyword to explore current studies.
""")

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("Search")
    search_term = st.text_input(
        "Drug, disease, company, etc.",
        placeholder="e.g., Alzheimer, CAR-T, Phase 1"
    )

    display_n = st.slider("Number of results", 10, 100, 25, step=5)


# ============================================================
# FETCH DATA
# ============================================================
expr = search_term.strip() if search_term.strip() else "phase"

try:
    df = fetch_trials(expr, max_rnk=200)
except Exception as e:
    st.error("Unable to load trial data.")
    st.stop()

if df.empty:
    st.warning("No trials found. Try a different search.")
    st.stop()

df = df.head(display_n)


# ============================================================
# LAYOUT
# ============================================================
col1, col2 = st.columns([1.3, 2])

# ------------------------------------------------------------
# LEFT: TRIAL SELECTION LIST
# ------------------------------------------------------------
with col1:
    st.subheader("Select a Trial")

    options = [
        f"{row['NCT ID']} — {row['Title'][:65]}{'…' if len(row['Title']) > 65 else ''}"
        for _, row in df.iterrows()
    ]

    selected_label = st.radio("", options, index=0)
    selected_nct = selected_label.split(" — ")[0]

    selected_row = df[df["NCT ID"] == selected_nct].iloc[0]


# ------------------------------------------------------------
# RIGHT: TRIAL DETAILS + ARTICLES
# ------------------------------------------------------------
with col2:
    st.subheader("Trial Details")

    row = selected_row

    st.markdown(f"### {row['Title']}")

    st.write(f"**Drug / Intervention:** {row['Intervention / Drug'] or '—'}")
    st.write(f"**Condition(s):** {row['Condition'] or '—'}")
    st.write(f"**Phase:** {row['Phase'] or '—'}")
    st.write(f"**Status:** {row['Status'] or '—'}")
    st.write(f"**Sponsor:** {row['Sponsor'] or '—'}")

    st.write("---")
    st.write(f"**Start Date:** {row['Start Date'] or '—'}")
    st.write(f"**Last Updated:** {row['Last Updated'] or '—'}")

    location = ", ".join([row["City"], row["State"], row["Country"]]).strip(", ")
    if location:
        st.write(f"**Location:** {location}")

    st.markdown(f"[View Full Study ➜]({row['CT Link']})")

    st.write("---")

    # News Section
    st.subheader("Related Articles")

    with st.spinner("Loading articles…"):
        articles = fetch_articles(row["Intervention / Drug"], row["Condition"])

    if not articles:
        st.write("No recent news found.")
    else:
        for a in articles:
            st.markdown(f"**[{a['title']}]({a['link']})**")

            if a["published"]:
                st.caption(a["published"])

            if a["summary"]:
                st.write(a["summary"] + "...")

            st.write("---")
