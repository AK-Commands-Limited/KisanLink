<<<<<<< HEAD
# KisaanLink website

`app.py` is retained unchanged as the original Streamlit market-price dashboard on port 8501. The new website entry point is `index.html`, served by `server.py` so the Excel workbooks are never exposed as public downloads. User profiles are stored privately in `User_info.xlsx`; each save updates its matching user row.

## Run

1. Install dependencies: `python -m pip install -r requirements.txt`
2. Start the website: `python server.py`
3. Open `http://127.0.0.1:5000` (do not open `index.html` directly or through Live Server).

The supplied test account is `test_farmer` / `Farmer@123`. Change or remove it before public use. Passwords are hashed. `User_info.xlsx`, `marketplace.db`, and `.env` are ignored by Git and never served as public files.

The site reads only the `Market_prices` worksheet on the server. It supplies filtered results and timelines to the browser, preserving the existing State → District → Market → Commodity → Variety calculation flow. The original dashboard remains available with `streamlit run app.py` at `http://localhost:8501/`. Listings start empty deliberately, as no product data was supplied.

## GitHub and deployment

Push this folder to GitHub; it includes a GitHub Actions verification workflow. Do **not** use GitHub Pages because it cannot run Flask, login, or Excel writes. Instead, create a Render service from the GitHub repository. Render automatically reads `render.yaml`, starts the app with Gunicorn, creates `AGRI_SECRET_KEY`, and mounts a persistent `/var/data` disk for `User_info.xlsx` and marketplace listings.
=======
# KisaanLink
>>>>>>> 193e1f0d10e6dd04d8b154d8c8ffeef06161c636
