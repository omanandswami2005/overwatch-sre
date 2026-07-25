import streamlit as st

import theme
from views import landing_page, main_page

st.set_page_config(page_title="Overwatch - Your SRE Copilot", page_icon="🩺", layout="wide")
theme.inject()

landing_pg = st.Page(landing_page.render, title="Overwatch - Your SRE Copilot", url_path="", default=True)
main_pg = st.Page(main_page.render, title="Console", url_path="main")

# each view needs a reference to the other page's st.Page object for
# st.page_link() — can't exist at import time since they're circular,
# so wire them up here before the navigation router runs either page.
landing_page.MAIN_PAGE = main_pg
main_page.LANDING_PAGE = landing_pg

router = st.navigation([landing_pg, main_pg], position="hidden")
router.run()
