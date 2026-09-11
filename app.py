import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path
from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash

# Page configuration
st.set_page_config(page_title="Market Price Dashboard", layout="wide")

ROOT = Path(__file__).parent
USER_FILE = ROOT / "User_info.xlsx"
USER_COLUMNS = ["user_id", "username", "password_hash", "name", "business_name", "phone", "location", "farm_info", "created_at", "record_reference"]


def load_users():
    if not USER_FILE.exists():
        test_user = pd.DataFrame([["test-farmer-001", "test_farmer", generate_password_hash("Farmer@123"), "Test Farmer", "", "", "", "", datetime.now(timezone.utc).isoformat(), "SE-20260911-TEST_FARMER"]], columns=USER_COLUMNS)
        test_user.to_excel(USER_FILE, sheet_name="Users", index=False)
    return pd.read_excel(USER_FILE, sheet_name="Users", dtype=str).fillna("")


def save_users(users):
    users.to_excel(USER_FILE, sheet_name="Users", index=False)


def show_login():
    st.title("🌾 KisaanLink")
    st.subheader("Sign in to access Market Price Analysis")
    st.caption("Your profile information is saved privately in User_info.xlsx. Passwords are stored as hashes.")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        users = load_users()
        match = users[users["username"].str.casefold() == username.strip().casefold()]
        if match.empty:
            st.error("Username not found.")
        elif not check_password_hash(match.iloc[0]["password_hash"], password):
            st.error("Wrong password.")
        else:
            st.session_state.user_id = match.iloc[0]["user_id"]
            st.rerun()
    st.info("Test account: username `test_farmer` · password `Farmer@123`")


users = load_users()
if "user_id" not in st.session_state:
    show_login()
    st.stop()

current = users[users["user_id"] == st.session_state.user_id]
if current.empty:
    st.session_state.clear()
    st.rerun()
current = current.iloc[0]

st.title("🌾 Agricultural Market Price Analysis Dashboard")
st.markdown("Select options from the dropdown hierarchy below to view modal prices and timeline trends.")

# Load data cache to optimize performance
@st.cache_data
def load_data():
    file_path = "Market_prices.csv.xlsx"
    df = pd.read_excel(file_path, sheet_name="Market_prices")
    # Ensure arrival_date is in datetime format for timeline plotting
    df['arrival_date'] = pd.to_datetime(df['arrival_date'])
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"Error loading file: {e}. Please ensure 'Market_prices.csv.xlsx' is in the directory.")
    st.stop()

# 1. Cascading Dropdown Hierarchy: State > District > Market > Commodity > Variety
st.sidebar.header("🔍 Filter Selection")
st.sidebar.success(f"Signed in as {current['name'] or current['username']}")
if st.sidebar.button("Log out"):
    st.session_state.clear()
    st.rerun()
with st.sidebar.expander("My Profile"):
    with st.form("profile"):
        name = st.text_input("Name", value=current["name"])
        business_name = st.text_input("Farmer / business name", value=current["business_name"])
        phone = st.text_input("Phone", value=current["phone"])
        location = st.text_input("Location", value=current["location"])
        farm_info = st.text_area("Farm information", value=current["farm_info"])
        save_profile = st.form_submit_button("Save profile")
    if save_profile:
        mask = users["user_id"] == st.session_state.user_id
        users.loc[mask, ["name", "business_name", "phone", "location", "farm_info"]] = [name.strip(), business_name.strip(), phone.strip(), location.strip(), farm_info.strip()]
        save_users(users)
        st.success(f"Profile saved. Reference: {current['record_reference']}")

# State Dropdown
states = sorted(df['state'].dropna().unique())
selected_state = st.sidebar.selectbox("1. Select State", states)

# District Dropdown (filtered by State)
districts = sorted(df[df['state'] == selected_state]['district'].dropna().unique())
selected_district = st.sidebar.selectbox("2. Select District", districts)

# Market Dropdown (filtered by District)
markets = sorted(df[(df['state'] == selected_state) & (df['district'] == selected_district)]['market'].dropna().unique())
selected_market = st.sidebar.selectbox("3. Select Market", markets)

# Commodity Dropdown (filtered by Market)
commodities = sorted(df[(df['state'] == selected_state) & 
                        (df['district'] == selected_district) & 
                        (df['market'] == selected_market)]['commodity'].dropna().unique())
selected_commodity = st.sidebar.selectbox("4. Select Commodity", commodities)

# Variety Dropdown (filtered by Commodity)
varieties = sorted(df[(df['state'] == selected_state) & 
                      (df['district'] == selected_district) & 
                      (df['market'] == selected_market) & 
                      (df['commodity'] == selected_commodity)]['variety'].dropna().unique())
selected_variety = st.sidebar.selectbox("5. Select Variety", varieties)

# Filter dataframe based on selections
filtered_df = df[
    (df['state'] == selected_state) & 
    (df['district'] == selected_district) & 
    (df['market'] == selected_market) & 
    (df['commodity'] == selected_commodity) & 
    (df['variety'] == selected_variety)
].sort_values('arrival_date')

# Main Panel Display
st.subheader("📊 Selection Summary & Modal Price")

if filtered_df.empty:
    st.warning("No data available for the selected combination.")
else:
    # Display current/latest modal price
    latest_row = filtered_df.iloc[-1]
    col1, col2, col3 = st.columns(3)
    col1.metric("Latest Modal Price", f"₹ {latest_row['modal_price']:,.2f}")
    col2.metric("Min Price", f"₹ {latest_row['min_price']:,.2f}")
    col3.metric("Max Price", f"₹ {latest_row['max_price']:,.2f}")

    st.markdown("---")
    
    # 2. Timeline Graph on Modal Prices
    st.subheader("📈 Modal Price Timeline")
    
    if len(filtered_df['arrival_date'].unique()) > 1:
        fig = px.line(
            filtered_df, 
            x='arrival_date', 
            y='modal_price', 
            markers=True,
            title=f"Modal Price Trend for {selected_commodity} ({selected_variety}) in {selected_market}",
            labels={'arrival_date': 'Timeline (Arrival Date)', 'modal_price': 'Modal Price (₹)'}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        # If dataset currently contains a single date point, display bar/scatter point with timeline notice
        fig = px.scatter(
            filtered_df, 
            x='arrival_date', 
            y='modal_price',
            size=[15],
            title=f"Modal Price for {selected_commodity} ({selected_variety}) in {selected_market}",
            labels={'arrival_date': 'Timeline (Arrival Date)', 'modal_price': 'Modal Price (₹)'}
        )
        fig.update_traces(marker=dict(size=12))
        st.plotly_chart(fig, use_container_width=True)
        st.info("Note: The current dataset contains data for a single timeline date. As historical dates are added to your XLSX file, this chart will automatically render a continuous timeline trend.")

    # Show underlying filtered records
    with st.expander("View Raw Data Records"):
        st.dataframe(filtered_df)
