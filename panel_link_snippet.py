
# ── Enophia: Agent Kontrol Paneli linki (MPT Main.py sonuna eklenir) ──
# PANEL_URL env'i verilirse Streamlit sidebar'ına panele geçiş butonu koyar.
try:
    import os as _enophia_os
    import streamlit as _enophia_st

    _enophia_panel_url = _enophia_os.environ.get("PANEL_URL", "").strip()
    if _enophia_panel_url:
        _enophia_st.sidebar.markdown("---")
        try:
            _enophia_st.sidebar.link_button(
                "🎛️ Agent Kontrol Paneli", _enophia_panel_url
            )
        except Exception:
            _enophia_st.sidebar.markdown(
                f"### 🎛️ [Agent Kontrol Paneli →]({_enophia_panel_url})"
            )
except Exception:
    pass
