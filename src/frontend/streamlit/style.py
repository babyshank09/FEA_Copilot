custom_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400..700&family=Google+Sans+Code:wght@400..500&display=swap');

/* ═══════════════════════════════════════════════════════════════════
   FEA COPILOT — design tokens
   Palette lifted from the Salford reference: void black -> electric
   blue, pure white type, thin luminous arcs.
   ═══════════════════════════════════════════════════════════════════ */
:root {
    --void:        #04070E;
    --deep:        #070C18;
    --elev:        #0B1220;
    --elev-2:      #111A2C;

    /* Sampled from Gemini's dark UI */
    --gemini-sidebar: #1F1F1F;
    --gemini-input:   #1E1F20;

    --blue-core:   #2F6BFF;
    --blue-bright: #5B8CFF;
    --blue-deep:   #1D4ED8;
    --blue-wash:   rgba(47, 107, 255, 0.14);

    --text-hi:     #FFFFFF;
    --text:        #C6D2E8;
    --text-dim:    #7B8AA6;
    --text-faint:  #4C5A75;

    --stroke:      rgba(255, 255, 255, 0.09);
    --stroke-hi:   rgba(255, 255, 255, 0.16);
    --glass:       rgba(255, 255, 255, 0.035);

    --glow-sm:     0 0 14px rgba(47, 107, 255, 0.35);
    --glow-md:     0 0 28px rgba(47, 107, 255, 0.42);
    --glow-lg:     0 0 60px rgba(47, 107, 255, 0.30);

    --ease:        cubic-bezier(0.22, 1, 0.36, 1);
    --radius:      14px;

    /* Gemini's typefaces */
    --font-display: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-body:    'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono:    'Google Sans Code', 'SF Mono', Menlo, monospace;
}

/* ═══ 1. CANVAS ══════════════════════════════════════════════════ */
.stApp {
    background:
        radial-gradient(1200px 820px at 10% 82%, rgba(47,107,255,0.50), transparent 62%),
        radial-gradient(900px 700px at 42% 104%, rgba(59,130,246,0.30), transparent 66%),
        radial-gradient(700px 600px at 88% 6%, rgba(29,78,216,0.16), transparent 70%),
        linear-gradient(158deg, var(--void) 0%, var(--deep) 42%, #081026 100%) !important;
    background-attachment: fixed !important;
    font-family: var(--font-body) !important;
    color: var(--text) !important;
}

/* Concentric arcs removed — the gradient carries the canvas on its own */
[data-testid="stAppViewContainer"]::before,
[data-testid="stAppViewContainer"]::after {
    content: none !important;
}

/* Keep real content above the canvas */
[data-testid="stMain"] .block-container { position: relative; z-index: 1; }

/* ═══ 2. STREAMLIT CHROME ════════════════════════════════════════ */
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { right: 12px; }
#MainMenu, footer { visibility: hidden; }

/* Hide only the deploy button and decoration bar — NOT the whole
   toolbar, since the sidebar expand control lives inside stToolbar
   too and would get taken out along with it. */
[data-testid="stAppDeployButton"],
[data-testid="stDecoration"] {
    display: none !important;
}

/* Material-symbol ligatures render as raw words ("upload", "face",
   "smart_toy") whenever the icon font is unavailable. Clip them to the
   glyph box so a missing font can never spill text across the layout —
   this only constrains stray text, it does not hide any button. */
[data-testid="stIconMaterial"] {
    overflow: hidden !important;
    max-width: 1em !important;
    max-height: 1em !important;
    line-height: 1 !important;
    white-space: nowrap !important;
}

/* Content column. Streamlit restyles this container depending on whether
   a bottom container exists (hasBottom — true only while st.chat_input is
   on screen), so the column jumped wider on the file-upload step where the
   uploader replaces the chat input. max-width is pinned with !important so
   the width is identical in every state; this one value is the dial. */
[data-testid="stMain"] .block-container,
[data-testid="stMainBlockContainer"] {
    padding-top: 2.6rem !important;
    padding-bottom: 7rem !important;
    max-width: 46rem !important;
}
/* Keep the chat input the same width as the messages above it */
[data-testid="stBottomBlockContainer"] {
    max-width: 46rem !important;
}

/* ═══ 3. TYPOGRAPHY ══════════════════════════════════════════════ */
h1, h2, h3, h4, [data-testid="stHeading"] {
    font-family: var(--font-display) !important;
    color: var(--text-hi) !important;
    letter-spacing: -0.03em !important;
}

/* ── Logo lockup (replaces the st.title wordmark) ──
   Keyed containers from main.py: st.container(key="hero_logo") in the
   main pane, key="sidebar_logo" in the sidebar. Section 12's generic
   image framing would otherwise put a border and shadow around it. */
.st-key-hero_logo [data-testid="stImage"] img,
.st-key-sidebar_logo [data-testid="stImage"] img {
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    height: auto !important;
    max-width: 100% !important;
    animation: riseIn 0.7s var(--ease) both;
}
/* Display size lives here, not in st.image(width=...) — Streamlit
   resizes the served bitmap to an int width and it goes soft on
   high-DPI screens. Scaling the full-resolution file down in the
   browser keeps it crisp. */
.st-key-hero_logo [data-testid="stImage"] img { width: 430px !important; }
.st-key-sidebar_logo [data-testid="stImage"] img { width: 200px !important; }
.st-key-hero_logo { margin-bottom: 0.5rem !important; }
.st-key-sidebar_logo { margin: 0.15rem 0 0.35rem !important; }

/* Empty-thread greeting from main.py: st.container(key="empty_state_greeting").
   UI-only — shown while the thread has no messages in graph state. */
.st-key-empty_state_greeting {
    margin-top: 30vh !important;
}
.st-key-empty_state_greeting p {
    font-size: 2.3rem !important;
    font-weight: 100 !important;
    line-height: 1.15 !important;
    background: linear-gradient(96deg, #FFFFFF 12%, #BBD0FF 48%, var(--blue-bright) 92%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: riseIn 0.7s var(--ease) both;
}

/* App title — the wordmark treatment */
[data-testid="stMain"] h1 {
    font-size: 3.05rem !important;
    font-weight: 800 !important;
    line-height: 1.02 !important;
    margin-bottom: 0.15rem !important;
    background: linear-gradient(96deg, #FFFFFF 12%, #BBD0FF 48%, var(--blue-bright) 92%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: riseIn 0.7s var(--ease) both;
}

/* Tagline under the title */
[data-testid="stMain"] h1 + div [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stText"] {
    color: var(--text-dim) !important;
    font-size: 0.86rem !important;
    letter-spacing: 0.16em !important;
    text-transform: uppercase !important;
    font-weight: 500 !important;
    animation: riseIn 0.7s var(--ease) 0.08s both;
}

p, li, span, label { font-family: var(--font-body) !important; }
code, pre, [data-testid="stCode"] {
    font-family: var(--font-mono) !important;
    font-size: 0.83rem !important;
}
pre {
    background: rgba(0, 0, 0, 0.42) !important;
    border: 1px solid var(--stroke) !important;
    border-radius: 12px !important;
}
code { color: var(--blue-bright) !important; }

/* ═══ 4. SIDEBAR ═════════════════════════════════════════════════ */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background: var(--gemini-sidebar) !important;
}
[data-testid="stSidebar"] {
    border-right: none !important;
}
[data-testid="stSidebar"] h1 {
    font-size: 1.32rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
    color: var(--text-hi) !important;
}
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.17em !important;
    text-transform: uppercase !important;
    color: var(--text-faint) !important;
    margin-top: 1.5rem !important;
}
[data-testid="stSidebar"] label {
    font-size: 0.78rem !important;
    color: var(--text-dim) !important;
    font-weight: 500 !important;
}

/* ── Sidebar collapse / expand chevrons ──
   Both controls draw their arrow with a Material Symbols ligature that
   this deployment fails to resolve, so the raw word leaks through as
   text. Drop the icon span and draw a font-independent chevron in its
   place — exactly one glyph either way. Hide every child, not just the
   icon: its wrapper span keeps its width otherwise and pushes the
   glyph off-centre. */
[data-testid="stExpandSidebarButton"] > *,
[data-testid="stSidebarCollapseButton"] button > * {
    display: none !important;
}
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"] button {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 32px !important;
    height: 32px !important;
    padding: 0 !important;
    background: var(--glass) !important;
    border: 1px solid var(--stroke) !important;
    border-radius: 9px !important;
    color: var(--text-hi) !important;
    transition: background 0.25s var(--ease), border-color 0.25s var(--ease) !important;
}
[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stSidebarCollapseButton"] button:hover {
    background: rgba(255, 255, 255, 0.08) !important;
    border-color: var(--stroke-hi) !important;
}
[data-testid="stExpandSidebarButton"]::before,
[data-testid="stSidebarCollapseButton"] button::before {
    font-family: var(--font-body) !important;
    font-size: 16px !important;
    font-weight: 700 !important;
    line-height: 1 !important;
    color: var(--text-hi) !important;
}
[data-testid="stExpandSidebarButton"]::before { content: "\\00BB"; }
[data-testid="stSidebarCollapseButton"] button::before { content: "\\00AB"; }
/* No hover sweep on these small controls */
[data-testid="stExpandSidebarButton"]::after,
[data-testid="stSidebarCollapseButton"] button::after { content: none !important; }

/* ═══ 5. BUTTONS ═════════════════════════════════════════════════ */
[data-testid^="stBaseButton"] {
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em !important;
    border-radius: 11px !important;
    transition: transform 0.18s var(--ease), box-shadow 0.28s var(--ease),
                background 0.28s var(--ease), border-color 0.28s var(--ease) !important;
    position: relative;
    overflow: hidden;
}
/* Secondary */
[data-testid^="stBaseButton-secondary"] {
    background: var(--glass) !important;
    border: 1px solid var(--stroke) !important;
    color: var(--text) !important;
}
[data-testid^="stBaseButton-secondary"]:hover {
    background: rgba(255, 255, 255, 0.075) !important;
    border-color: var(--stroke-hi) !important;
    color: var(--text-hi) !important;
    transform: translateY(-1px);
}
/* Primary — electric, with a light sweep on hover */
[data-testid^="stBaseButton-primary"] {
    background: linear-gradient(135deg, var(--blue-core), var(--blue-deep)) !important;
    border: 1px solid rgba(120, 160, 255, 0.42) !important;
    color: #FFFFFF !important;
    box-shadow: var(--glow-sm), inset 0 1px 0 rgba(255,255,255,0.16) !important;
}
[data-testid^="stBaseButton-primary"]:hover {
    transform: translateY(-1px);
    box-shadow: var(--glow-md), inset 0 1px 0 rgba(255,255,255,0.22) !important;
}
[data-testid^="stBaseButton"]::after {
    content: "";
    position: absolute; inset: 0;
    background: linear-gradient(110deg, transparent 30%, rgba(255,255,255,0.20) 50%, transparent 70%);
    transform: translateX(-120%);
    transition: transform 0.75s var(--ease);
}
[data-testid^="stBaseButton"]:hover::after { transform: translateX(120%); }
[data-testid^="stBaseButton"]:active { transform: translateY(0) scale(0.985); }

/* ═══ 6. INPUTS ══════════════════════════════════════════════════ */
/* Streamlit draws the border on these wrappers, not on the inner field,
   so style the wrapper — styling the field as well gave two borders. */
[data-testid="stTextInputRootElement"],
[data-testid="stNumberInputContainer"],
[data-testid="stTextAreaRootElement"],
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {
    background: rgba(255, 255, 255, 0.045) !important;
    border: 1px solid var(--stroke) !important;
    border-radius: 11px !important;
    color: var(--text-hi) !important;
    font-family: var(--font-body) !important;
    transition: border-color 0.25s var(--ease), box-shadow 0.25s var(--ease),
                background 0.25s var(--ease) !important;
}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: var(--text-hi) !important;
    font-family: var(--font-body) !important;
}
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within {
    border-color: var(--blue-core) !important;
    box-shadow: 0 0 0 3px var(--blue-wash), var(--glow-sm) !important;
    background: rgba(47, 107, 255, 0.06) !important;
    outline: none !important;
}
[data-testid="stSelectbox"] > div > div:hover,
[data-testid="stMultiSelect"] > div > div:hover {
    border-color: var(--stroke-hi) !important;
}
[data-testid="stSlider"] [role="slider"] {
    background: var(--blue-core) !important;
    box-shadow: var(--glow-sm) !important;
}

/* ═══ 7. FILE UPLOADER ═══════════════════════════════════════════ */
[data-testid="stFileUploaderDropzone"] {
    background: rgba(47, 107, 255, 0.045) !important;
    border: 1.5px dashed rgba(91, 140, 255, 0.34) !important;
    border-radius: var(--radius) !important;
    transition: border-color 0.3s var(--ease), background 0.3s var(--ease),
                box-shadow 0.3s var(--ease) !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--blue-bright) !important;
    background: rgba(47, 107, 255, 0.10) !important;
    box-shadow: var(--glow-sm), inset 0 0 40px rgba(47,107,255,0.07) !important;
}
/* Uploaded-file rows sit as siblings of the dropzone (no stable testid) */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] ~ div {
    animation: riseIn 0.4s var(--ease) both;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] ~ div li,
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] ~ div > div {
    background: var(--glass) !important;
    border: 1px solid var(--stroke) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] { color: var(--text-dim) !important; }
/* Drop the dropzone's icon glyph — it was doubling up with the button
   label as "uploadUpload" */
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] {
    display: none !important;
}

/* ═══ 8. CHAT MESSAGES ═══════════════════════════════════════════ */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 6px 0 !important;
    display: flex !important;
    width: 100% !important;
    animation: messageIn 0.5s var(--ease) both;
}
[data-testid="stChatMessageContent"] {
    display: flex !important;
    flex-direction: column !important;
    width: 100% !important;
}
/* Avatars off — Streamlit paints these as red/orange squares holding
   :material/face: and :material/smart_toy:, which this deployment
   renders as the literal words spilling over the messages. The prefix
   match covers the User, Assistant and Custom variants. */
[data-testid^="stChatMessageAvatar"],
[data-testid="stChatMessage"] > img:first-child {
    display: none !important;
}

/* USER — right aligned, cool glass */
[data-testid="stChatMessage"]:has(div[aria-label="Chat message from user"]) {
    flex-direction: row-reverse !important;
}
[data-testid="stChatMessage"]:has(div[aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] {
    align-items: flex-end !important;
    margin-right: 0 !important;
    margin-left: auto !important;
}
[data-testid="stChatMessage"]:has(div[aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] > div {
    background: rgba(255, 255, 255, 0.055) !important;
    border: 1px solid var(--stroke) !important;
    color: var(--text-hi) !important;
    border-radius: 16px !important;
    padding: 11px 16px !important;
    width: fit-content !important;
    max-width: 68% !important;
    text-align: left !important;
    backdrop-filter: blur(10px);
}

/* ASSISTANT — left aligned, bare text with no bubble */
[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) {
    flex-direction: row !important;
}
[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) [data-testid="stChatMessageContent"] {
    align-items: flex-start !important;
    margin-left: 0 !important;
    margin-right: auto !important;
}
[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) [data-testid="stChatMessageContent"] > div {
    background: none !important;
    border: none !important;
    color: var(--text-hi) !important;
    border-radius: 0 !important;
    padding: 2px 0 !important;
    width: 100% !important;
    max-width: 100% !important;
    text-align: left !important;
    box-shadow: none !important;
    backdrop-filter: none !important;
}

/* ═══ 9. CHAT INPUT ══════════════════════════════════════════════ */
[data-testid="stBottom"] { background: transparent !important; }
/* Scrim that hides messages scrolling under the input. It starts above
   the bottom container (::before) and ramps on an eased curve, so there
   is no visible edge where it begins. The ::before ends at 0.40 and the
   container starts at 0.40, so the seam between them is seamless. */
[data-testid="stBottom"] > div {
    position: relative;
    background: linear-gradient(180deg,
        rgba(4,7,14,0.40) 0%,
        rgba(4,7,14,0.62) 30%,
        rgba(4,7,14,0.80) 60%,
        rgba(4,7,14,0.92) 100%) !important;
}
[data-testid="stBottom"] > div::before {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    bottom: 100%;
    height: 8rem;
    pointer-events: none;
    background: linear-gradient(180deg,
        rgba(4,7,14,0)    0%,
        rgba(4,7,14,0.04) 20%,
        rgba(4,7,14,0.12) 45%,
        rgba(4,7,14,0.25) 70%,
        rgba(4,7,14,0.40) 100%);
}
[data-testid="stChatInput"] {
    background: var(--gemini-input) !important;
    /* Transparent rather than none so the focus border below can still show */
    border: 1px solid transparent !important;
    /* Pill: the browser clamps this to half the height, so the ends are
       always full semicircles whatever the box size */
    border-radius: 9999px !important;
    padding-left: 0.75rem !important;
    padding-right: 0.4rem !important;
    transition: border-color 0.3s var(--ease), box-shadow 0.3s var(--ease) !important;
}
/* Streamlit draws its own filled, bordered, rounded box on this inner div
   (with a blue :focus-within border). Strip it so the pill above is the
   only shape drawn. */
[data-testid="stChatInput"] > div {
    background: transparent !important;
    border: none !important;
    border-radius: inherit !important;
}
[data-testid="stChatInputSubmitButton"] { border-radius: 9999px !important; }
[data-testid="stChatInput"]:focus-within {
    border-color: rgba(91, 140, 255, 0.62) !important;
    box-shadow: 0 0 0 3px var(--blue-wash), var(--glow-md) !important;
}
[data-testid="stChatInput"] textarea {
    color: var(--text-hi) !important;
    font-size: 1rem !important;   /* Streamlit default is 0.875rem */
}
/* Gemini's placeholder grey, sampled from its UI */
[data-testid="stChatInput"] textarea::placeholder { color: #BEC1C6 !important; }

/* ═══ 10. WORKING / THINKING STATES ══════════════════════════════ */
/* st.spinner — used for storage init and document embedding */
[data-testid="stSpinner"] {
    color: var(--text-dim) !important;
    font-size: 0.86rem !important;
}
[data-testid="stSpinner"] > div > i {
    border-color: var(--blue-core) transparent transparent transparent !important;
    filter: drop-shadow(0 0 6px rgba(47,107,255,0.65));
}
/* Status line streamed from the graph writer: an isolated markdown
   element with no surrounding chat message. Gets a shimmering sweep so
   the agent visibly "thinks" between dispatches. */
[data-testid="stMain"] [data-testid="stElementContainer"]:not(:has([data-testid="stChatMessage"]))
    > [data-testid="stMarkdownContainer"] > p:only-child {
    color: var(--text-dim) !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.01em;
    background: linear-gradient(90deg, var(--text-faint) 20%, var(--blue-bright) 50%, var(--text-faint) 80%);
    background-size: 220% auto;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shimmer 2.4s linear infinite;
}
/* Streamlit's own "running" indicator */
[data-testid="stStatusWidget"] {
    background: var(--elev) !important;
    border: 1px solid var(--stroke) !important;
    border-radius: 10px !important;
}

/* ═══ 11. EXPANDER (graph viewer) ════════════════════════════════ */
[data-testid="stExpander"] {
    background: var(--glass) !important;
    border: 1px solid var(--stroke) !important;
    border-radius: var(--radius) !important;
    overflow: hidden;
    transition: border-color 0.3s var(--ease), box-shadow 0.3s var(--ease) !important;
}
[data-testid="stExpander"]:hover {
    border-color: var(--stroke-hi) !important;
    box-shadow: 0 8px 34px rgba(0, 0, 0, 0.3);
}
[data-testid="stExpander"] summary {
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    color: var(--text-dim) !important;
}
[data-testid="stExpander"] summary:hover { color: var(--blue-bright) !important; }

/* ═══ 12. OUTPUT WIDGETS (interface agent) ═══════════════════════ */
[data-testid="stVegaLiteChart"],
[data-testid="stDataFrame"],
[data-testid="stTable"],
[data-testid="stJson"] {
    background: rgba(8, 13, 24, 0.62) !important;
    border: 1px solid var(--stroke) !important;
    border-radius: var(--radius) !important;
    padding: 12px !important;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.34);
    animation: riseIn 0.55s var(--ease) both;
}
[data-testid="stVegaLiteChart"]:hover,
[data-testid="stDataFrame"]:hover {
    border-color: rgba(91, 140, 255, 0.30) !important;
    box-shadow: 0 10px 46px rgba(0,0,0,0.4), var(--glow-lg);
}
[data-testid="stMetric"] {
    background: linear-gradient(145deg, rgba(47,107,255,0.11), rgba(255,255,255,0.02)) !important;
    border: 1px solid rgba(91, 140, 255, 0.22) !important;
    border-radius: var(--radius) !important;
    padding: 16px 18px !important;
    animation: riseIn 0.55s var(--ease) both;
}
[data-testid="stMetricLabel"] {
    color: var(--text-dim) !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.13em !important;
    text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
    font-family: var(--font-display) !important;
    font-weight: 800 !important;
    color: var(--text-hi) !important;
    text-shadow: 0 0 26px rgba(91, 140, 255, 0.4);
}
[data-testid="stImage"] img {
    border-radius: var(--radius) !important;
    border: 1px solid var(--stroke) !important;
    box-shadow: 0 12px 46px rgba(0, 0, 0, 0.46);
    animation: riseIn 0.6s var(--ease) both;
}

/* ═══ 13. ALERTS ═════════════════════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border: 1px solid var(--stroke) !important;
    background: var(--glass) !important;
    backdrop-filter: blur(10px);
    animation: riseIn 0.4s var(--ease) both;
}

/* ═══ 14. SCROLLBAR & SELECTION ══════════════════════════════════ */
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: rgba(91, 140, 255, 0.22);
    border-radius: 8px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(91, 140, 255, 0.42); }
::selection { background: rgba(47, 107, 255, 0.36); color: #FFFFFF; }

/* ═══ 15. KEYFRAMES ══════════════════════════════════════════════ */
@keyframes messageIn {
    from { opacity: 0; transform: translateY(12px) scale(0.985); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes riseIn {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes shimmer {
    from { background-position: 220% center; }
    to   { background-position: -220% center; }
}

/* ═══ 16. ACCESSIBILITY ══════════════════════════════════════════ */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.001ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.001ms !important;
    }
}
</style>
"""





auth_css = """
    <style>
    /* No sidebar or expand control on the sign-in screen */
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="stExpandSidebarButton"] { display: none !important; }

    [data-testid="stMain"] .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 9vh !important;
        padding-bottom: 3rem !important;
    }

    /* ── Brand block above the card ── */
    .st-key-auth_brand {
        align-items: center !important;
        text-align: center;
        margin-bottom: 1.4rem !important;
    }
    .st-key-auth_brand [data-testid="stImage"] img {
        width: 340px !important;
        max-width: 100% !important;
        height: auto !important;
        border: none !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        filter: drop-shadow(0 0 28px rgba(91, 140, 255, 0.35));
        animation: riseIn 0.7s var(--ease) both;
    }
    .st-key-auth_brand [data-testid="stElementToolbar"] { display: none !important; }
    .st-key-auth_brand [data-testid="stMarkdownContainer"],
    .st-key-auth_footer [data-testid="stMarkdownContainer"] {
        width: 100% !important;
        text-align: center !important;
    }
    .st-key-auth_brand p {
        text-align: center !important;
        margin: 0.6rem 0 0 !important;
        color: var(--text-dim) !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.22em !important;
        text-transform: uppercase !important;
        animation: riseIn 0.7s var(--ease) 0.08s both;
    }

    /* ── Glass card ── */
    .st-key-auth_card {
        width: min(440px, 100%) !important;
        align-self: center !important;
        margin: 0 auto !important;
        padding: 1.6rem 1.8rem 1.4rem !important;
        background:
            linear-gradient(160deg, rgba(255,255,255,0.065), rgba(255,255,255,0.018)) !important;
        border: 1px solid var(--stroke) !important;
        border-radius: 22px !important;
        backdrop-filter: blur(22px) saturate(140%);
        -webkit-backdrop-filter: blur(22px) saturate(140%);
        box-shadow:
            0 30px 80px rgba(0, 0, 0, 0.55),
            0 0 0 1px rgba(91, 140, 255, 0.05),
            inset 0 1px 0 rgba(255, 255, 255, 0.08);
        position: relative;
        animation: riseIn 0.75s var(--ease) 0.12s both;
    }
    /* Thin luminous edge along the top of the card */
    .st-key-auth_card::before {
        content: "";
        position: absolute;
        top: -1px; left: 18%; right: 18%;
        height: 1px;
        background: linear-gradient(90deg, transparent, var(--blue-bright), transparent);
        box-shadow: 0 0 14px rgba(91, 140, 255, 0.7);
        pointer-events: none;
    }

    /* ── Segmented Log in / Sign up switch (st.tabs) ── */
    .st-key-auth_card [data-testid="stTabs"] [role="tablist"] {
        display: grid !important;
        grid-template-columns: 1fr 1fr;
        gap: 4px !important;
        padding: 4px !important;
        background: rgba(0, 0, 0, 0.32) !important;
        border: 1px solid var(--stroke) !important;
        border-radius: 12px !important;
        margin-bottom: 1.3rem !important;
    }
    .st-key-auth_card [data-baseweb="tab-highlight"],
    .st-key-auth_card [data-baseweb="tab-border"],
    .st-key-auth_card .react-aria-SelectionIndicator { display: none !important; }
    .st-key-auth_card [role="tab"] {
        justify-content: center !important;
        height: 38px !important;
        margin: 0 !important;
        padding: 0 !important;
        border-radius: 9px !important;
        background: transparent !important;
        transition: background 0.25s var(--ease), box-shadow 0.25s var(--ease) !important;
    }
    .st-key-auth_card [role="tab"] p {
        font-family: var(--font-display) !important;
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        color: var(--text-dim) !important;
        transition: color 0.25s var(--ease);
    }
    .st-key-auth_card [role="tab"]:hover p { color: var(--text-hi) !important; }
    .st-key-auth_card [role="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, rgba(47,107,255,0.30), rgba(29,78,216,0.22)) !important;
        box-shadow: inset 0 0 0 1px rgba(120, 160, 255, 0.35), 0 4px 18px rgba(47, 107, 255, 0.22) !important;
    }
    .st-key-auth_card [role="tab"][aria-selected="true"] p { color: var(--text-hi) !important; }

    /* ── Headings inside each tab ── */
    .st-key-auth_card h3 {
        font-size: 1.45rem !important;
        font-weight: 600 !important;
        margin: 0 0 0.1rem !important;
        padding: 0 !important;
    }
    .st-key-auth_card [data-testid="stCaptionContainer"] p {
        color: var(--text-dim) !important;
        font-size: 0.86rem !important;
        margin-bottom: 0.4rem !important;
    }

    /* ── Form ── */
    .st-key-auth_card [data-testid="stForm"] {
        border: none !important;
        padding: 0 !important;
        background: transparent !important;
    }
    .st-key-auth_card label p {
        font-size: 0.76rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.04em !important;
        color: var(--text-dim) !important;
    }
    .st-key-auth_card [data-testid="stTextInputRootElement"] {
        height: 44px !important;
        background: rgba(0, 0, 0, 0.28) !important;
    }
    .st-key-auth_card input::placeholder { color: var(--text-faint) !important; }

    /* Password reveal toggle: its Material Symbols ligature leaks through
       as text ("visibility") here, so draw the eye with an SVG mask instead. */
    .st-key-auth_card [data-testid="stTextInputRootElement"] button [data-testid="stIconMaterial"] {
        display: none !important;
    }
    .st-key-auth_card [data-testid="stTextInputRootElement"] button::before {
        content: "";
        width: 18px;
        height: 18px;
        background: var(--text-dim);
        -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z'/%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3C/svg%3E") center / contain no-repeat;
                mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z'/%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3C/svg%3E") center / contain no-repeat;
        transition: background 0.2s var(--ease);
    }
    .st-key-auth_card [data-testid="stTextInputRootElement"] button:hover::before {
        background: var(--text-hi);
    }
    .st-key-auth_card [data-testid="stTextInputRootElement"] button[aria-pressed="true"]::before {
        background: var(--blue-bright);
    }
    /* "Press Enter to submit form" hint */
    .st-key-auth_card [data-testid="InputInstructions"] { display: none !important; }

    .st-key-auth_card [data-testid="stCheckbox"] label p {
        font-size: 0.82rem !important;
        letter-spacing: 0 !important;
    }

    .st-key-auth_card [data-testid="stFormSubmitButton"] { margin-top: 0.5rem !important; }
    .st-key-auth_card [data-testid="stFormSubmitButton"] button {
        height: 46px !important;
        border-radius: 12px !important;
        font-size: 0.95rem !important;
    }

    /* ── Footer under the card ── */
    .st-key-auth_footer {
        margin-top: 1.4rem !important;
        text-align: center;
        animation: riseIn 0.7s var(--ease) 0.2s both;
    }
    .st-key-auth_footer p {
        color: var(--text-faint) !important;
        font-size: 0.74rem !important;
        letter-spacing: 0.03em;
    }
    </style>
    """