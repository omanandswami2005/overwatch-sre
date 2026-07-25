import streamlit as st

import theme
from views import docs_page, landing_page, main_page

st.set_page_config(page_title="Overwatch - Your SRE Copilot", page_icon="🩺", layout="wide")
theme.inject()

landing_pg = st.Page(landing_page.render, title="Overwatch - Your SRE Copilot", url_path="", default=True)
main_pg = st.Page(main_page.render, title="Console", url_path="main")
docs_pg = st.Page(docs_page.render, title="Architecture", url_path="docs")

# each view needs a reference to the other page's st.Page object for
# st.page_link() — can't exist at import time since they're circular,
# so wire them up here before the navigation router runs either page.
landing_page.MAIN_PAGE = main_pg
landing_page.DOCS_PAGE = docs_pg
main_page.LANDING_PAGE = landing_pg
main_page.DOCS_PAGE = docs_pg
docs_page.LANDING_PAGE = landing_pg
docs_page.MAIN_PAGE = main_pg

router = st.navigation([landing_pg, main_pg, docs_pg], position="hidden")
router.run()
