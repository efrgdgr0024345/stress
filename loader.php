<!doctype html>
<!-- Portable PHP view: valid HTML output under PHP, also served by the CAESAR API.
     All engineering data comes from authenticated same-origin /api/v1 endpoints. -->
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light" />
    <title>Load project · CAESAR</title>
    <style>
      :root {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #23252b;
        background: #f5f5f7;
        font-synthesis: none;
      }
      [hidden] {
        display: none !important;
      }
      * {
        box-sizing: border-box;
      }
      body {
        margin: 0;
      }
      button,
      select {
        font: inherit;
      }
      button,
      a,
      select {
        -webkit-tap-highlight-color: transparent;
      }
      button {
        cursor: pointer;
      }
      button:disabled {
        cursor: not-allowed;
        opacity: 0.45;
      }
      button:focus-visible,
      a:focus-visible,
      select:focus-visible {
        outline: 3px solid #94c5ff;
        outline-offset: 4px;
      }
      button {
        border: 0;
      }
      a {
        color: #0071e3;
        text-decoration: none;
      }
      a:hover {
        text-decoration: underline;
      }
      svg {
        width: 20px;
        height: 20px;
        fill: none;
        stroke: currentColor;
        stroke-width: 1.7;
        stroke-linecap: round;
        stroke-linejoin: round;
        flex-shrink: 0;
      }
      .symbols {
        display: none;
      }
      .topbar {
        height: 74px;
        border-bottom: 1px solid #e5e5eb;
        background: #ffffffbc;
        backdrop-filter: blur(24px);
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 max(24px, calc((100vw - 1120px) / 2));
        position: sticky;
        top: 0;
        z-index: 3;
      }
      .brand {
        display: flex;
        align-items: center;
        gap: 11px;
        font-weight: 700;
        color: #303139;
        font-size: 18px;
        letter-spacing: 0.5px;
      }
      .brand-mark {
        width: 34px;
        height: 34px;
        border-radius: 10px;
        background: linear-gradient(145deg, #63aeff, #0877ef);
        box-shadow: 0 3px 9px #0071e322;
        color: white;
        display: grid;
        place-items: center;
      }
      .brand small {
        display: block;
        letter-spacing: 1.4px;
        font-size: 8px;
        font-weight: 500;
        color: #92939d;
        margin-top: 4px;
      }
      .topbar-right {
        display: flex;
        gap: 18px;
        align-items: center;
        font-size: 12px;
      }
      .workspace-pill {
        display: flex;
        gap: 6px;
        align-items: center;
        color: #777983;
        background: #f0f1f5;
        border: 1px solid #e6e7ed;
        padding: 7px 10px;
        border-radius: 20px;
      }
      .workspace-pill i {
        height: 6px;
        width: 6px;
        background: #34c759;
        border-radius: 50%;
      }
      .content {
        max-width: 1120px;
        margin: 54px auto;
        padding: 0 24px 45px;
      }
      .eyebrow {
        font-size: 10px;
        font-weight: 650;
        color: #858792;
        letter-spacing: 1.8px;
      }
      .heading {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 24px;
        margin-bottom: 30px;
      }
      h1 {
        font-size: 40px;
        letter-spacing: -1.7px;
        font-weight: 680;
        line-height: 1.15;
        margin: 12px 0;
      }
      h2 {
        font-size: 24px;
        letter-spacing: -0.7px;
        margin: 0;
      }
      h3 {
        font-size: 15px;
        letter-spacing: -0.25px;
        margin: 0;
      }
      p {
        line-height: 1.7;
      }
      header p {
        color: #80828d;
        font-size: 14px;
        margin: 12px 0 0;
      }
      .back-link {
        font-size: 12px;
        display: flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
      }
      .back-link svg {
        width: 16px;
        height: 16px;
      }
      .loader-card {
        border: 1px solid #e5e6ed;
        border-radius: 19px;
        background: #ffffffdc;
        box-shadow: 0 6px 24px #1d243306;
        overflow: hidden;
      }
      .loader-main {
        display: grid;
        grid-template-columns: 1fr 280px;
        gap: 38px;
        padding: 32px;
      }
      .loader-icon {
        display: grid;
        place-items: center;
        width: 48px;
        height: 48px;
        color: #007aff;
        background: #e9f3ff;
        border-radius: 13px;
        margin-bottom: 18px;
      }
      .loader-icon svg {
        width: 26px;
        height: 26px;
      }
      .loader-description {
        font-size: 13px;
        color: #858791;
        margin: 9px 0 22px;
      }
      .project-controls {
        display: flex;
        gap: 11px;
      }
      select {
        width: 100%;
        min-width: 0;
        border: 1px solid #dddfe7;
        background: #fbfbfd;
        color: #52555f;
        padding: 12px 13px;
        border-radius: 9px;
        box-shadow: 0 1px 2px #00000004;
        font-size: 13px;
      }
      .button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        white-space: nowrap;
        background: linear-gradient(#238fff, #0074ec);
        color: white;
        padding: 12px 18px;
        border: 1px solid #0076ea;
        border-radius: 9px;
        font-weight: 550;
        font-size: 13px;
        box-shadow: 0 2px 5px #0071e31c;
      }
      .button:hover:not(:disabled) {
        background: #0071e3;
        text-decoration: none;
      }
      .button svg {
        width: 16px;
        height: 16px;
      }
      .hosting-panel {
        margin-top: 24px;
        border-top: 1px solid #e5e6ed;
        padding-top: 22px;
      }
      .hosting-panel h3 { display: flex; align-items: center; gap: 9px; }
      .hosting-panel h3 svg { width: 20px; height: 20px; color: #af52de; }
      .hosting-panel p, .install-guide { font-size: 13px; color: #656875; }
      .hosting-actions { display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }
      .button.secondary { background: #f4f4f8; color: #383b48; border-color: #dcdde5; box-shadow: none; }
      .button.secondary:hover { background: #e8e8f0; color: #383b48; }
      .install-guide { padding: 20px; border: 1px solid #e4def2; border-radius: 13px; background: #faf8ff; }
      .install-guide li { margin: 12px 0; line-height: 1.7; }
      .install-guide code { overflow-wrap: anywhere; color: #49406d; }
      .install-guide pre { overflow-x: auto; padding: 14px; background: #efedf5; border-radius: 8px; }
      .hosting-note { background: #fff6e8; border-radius: 9px; padding: 12px 14px; }
      .subtext {
        font-size: 11px;
        color: #8d8f99;
        display: flex;
        align-items: center;
        gap: 6px;
        margin: 15px 0 0;
      }
      .subtext svg {
        width: 13px;
        height: 13px;
      }
      .loader-info {
        background: linear-gradient(135deg, #f1f6ff, #f6f4fd);
        border: 1px solid #e8edf7;
        border-radius: 13px;
        padding: 21px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 13px;
      }
      .loader-info > svg {
        color: #9d8bdb;
        width: 29px;
        height: 29px;
      }
      .loader-info h3 {
        font-size: 14px;
        color: #626880;
      }
      .loader-info p {
        font-size: 12px;
        color: #9297a8;
        margin: 0;
      }
      .info-tags {
        display: flex;
        gap: 7px;
        flex-wrap: wrap;
      }
      .info-tags span {
        font-size: 9px;
        color: #8a91a5;
        border: 1px solid #e2e6f1;
        background: #fff9;
        padding: 4px 6px;
        border-radius: 5px;
      }
      .status {
        font-size: 12px;
        color: #62718a;
        line-height: 1.7;
        min-height: 21px;
        margin: 13px 0 0;
      }
      .status.error {
        color: #b56d45;
      }
      .lessons-heading {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin: 40px 0 20px;
      }
      .lessons-heading > div {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .lessons-heading p {
        font-size: 12px;
        color: #8c8f98;
        margin: 6px 0 0;
      }
      .count {
        font-size: 10px;
        color: #858b9a;
        background: #e9ebf1;
        border-radius: 6px;
        padding: 5px 8px;
      }
      .github-link {
        font-size: 11px;
        display: flex;
        gap: 5px;
        align-items: center;
        white-space: nowrap;
      }
      .github-link svg {
        width: 14px;
        height: 14px;
      }
      .lessons-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 17px;
      }
      .lesson {
        border-radius: 15px;
        border: 1px solid #e4e6ed;
        background: #fff;
        box-shadow: 0 3px 12px #26345203;
        padding: 23px;
        min-width: 0;
      }
      .lesson-top {
        display: flex;
        align-items: center;
        gap: 11px;
        margin-bottom: 17px;
      }
      .lesson-icon {
        width: 37px;
        height: 37px;
        border-radius: 11px;
        display: grid;
        place-items: center;
        background: var(--tint);
        color: var(--accent);
      }
      .lesson-meta {
        flex: 1;
      }
      .lesson-meta span {
        display: block;
        font-size: 10px;
        color: #9a9eab;
        letter-spacing: 0.5px;
      }
      .lesson-meta small {
        font-size: 10px;
        color: #9298a7;
        display: block;
        margin-top: 4px;
      }
      .adopted {
        font-size: 9px;
        color: #39a467;
        background: #edf8f1;
        border: 1px solid #e0f1e6;
        border-radius: 20px;
        padding: 5px 8px;
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .adopted svg {
        width: 10px;
        height: 10px;
      }
      .lesson h3 {
        font-size: 15px;
        color: #414756;
        font-weight: 620;
        line-height: 1.5;
      }
      .lesson-body {
        font-size: 12px;
        line-height: 1.85;
        color: #626b7b;
        margin: 10px 0 17px;
      }
      .lesson-action {
        border: 1px solid #eceef4;
        background: #f8f9fc;
        border-radius: 8px;
        padding: 12px;
        display: flex;
        align-items: flex-start;
        gap: 8px;
      }
      .lesson-action svg {
        height: 14px;
        width: 14px;
        color: var(--accent);
        margin-top: 2px;
      }
      .lesson-action b {
        font-size: 9px;
        color: #959ba9;
        display: block;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 5px;
        font-weight: 600;
      }
      .lesson-action p {
        font-size: 11px;
        color: #626d80;
        line-height: 1.8;
        margin: 0;
      }
      .lesson details {
        font-size: 10px;
        color: #9a9fab;
        margin-top: 13px;
        line-height: 1.8;
      }
      .lesson summary {
        cursor: pointer;
        list-style: none;
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .lesson summary svg {
        width: 12px;
        height: 12px;
      }
      .lesson details p {
        font-size: 10px;
        margin: 8px 0 0;
        overflow-wrap: anywhere;
      }
      .empty {
        padding: 35px;
        text-align: center;
        border: 1px dashed #dce1ed;
        border-radius: 13px;
        font-size: 13px;
        color: #8d96a9;
        grid-column: 1/-1;
      }
      .footer {
        margin-top: 29px;
        padding-top: 22px;
        border-top: 1px solid #e2e5ed;
        display: flex;
        justify-content: space-between;
        gap: 15px;
        font-size: 10px;
        color: #a0a6b3;
      }
      .footer > span {
        display: flex;
        align-items: center;
        gap: 5px;
      }
      .footer svg {
        width: 13px;
        height: 13px;
      }
      .loading {
        animation: pulse 1.3s ease-in-out infinite;
      }
      @keyframes pulse {
        50% {
          opacity: 0.4;
        }
      }
      @media (max-width: 760px) {
        .topbar {
          padding: 0 20px;
          height: 65px;
        }
        .content {
          margin-top: 30px;
          padding: 0 20px 30px;
        }
        .heading {
          display: block;
        }
        .heading .back-link {
          margin-top: 19px;
        }
        h1 {
          font-size: 32px;
        }
        .loader-main {
          grid-template-columns: 1fr;
          padding: 24px;
          gap: 24px;
        }
        .loader-info {
          display: none;
        }
        .lessons-grid {
          grid-template-columns: 1fr;
        }
        .lessons-heading {
          align-items: flex-start;
        }
        .lessons-heading h2 {
          font-size: 22px;
        }
        .lessons-heading p {
          font-size: 11px;
        }
        .github-link {
          font-size: 10px;
        }
        .workspace-pill {
          display: none;
        }
        .project-controls {
          flex-direction: column;
        }
        .button {
          min-height: 42px;
        }
        .lesson {
          padding: 21px;
        }
        .footer {
          font-size: 9px;
          flex-wrap: wrap;
        }
        .topbar-right {
          font-size: 10px;
        }
      }
      @media (prefers-reduced-motion: reduce) {
        .loading {
          animation: none;
        }
      }
    </style>
  </head>
  <body>
    <svg class="symbols" aria-hidden="true">
      <symbol id="layers" viewBox="0 0 24 24">
        <path d="m12 3 10 5-10 5L2 8 12 3Z" />
        <path d="m2 12 10 5 10-5M2 16l10 5 10-5" />
      </symbol>
      <symbol id="folder" viewBox="0 0 24 24">
        <path
          d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"
        />
      </symbol>
      <symbol id="arrow" viewBox="0 0 24 24">
        <path d="M5 12h14m-6-6 6 6-6 6" />
      </symbol>
      <symbol id="download" viewBox="0 0 24 24">
        <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />
      </symbol>
      <symbol id="external" viewBox="0 0 24 24">
        <path d="M8 5h11v11M19 5 5 19" />
      </symbol>
      <symbol id="shield" viewBox="0 0 24 24">
        <path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4Z" />
        <path d="m8 12 3 3 5-6" />
      </symbol>
      <symbol id="branch" viewBox="0 0 24 24">
        <circle cx="6" cy="5" r="3" />
        <circle cx="18" cy="6" r="3" />
        <circle cx="6" cy="19" r="3" />
        <path d="M6 8v8m0-3h5a7 7 0 0 0 7-7" />
      </symbol>
      <symbol id="book" viewBox="0 0 24 24">
        <path d="M3 4h6l3 3 3-3h6v16h-6l-3 2-3-2H3V4Zm9 3v15" />
      </symbol>
      <symbol id="check" viewBox="0 0 24 24">
        <path d="m5 12 4 4L19 6" />
      </symbol>
      <symbol id="box" viewBox="0 0 24 24">
        <path
          d="m12 2 9 5v10l-9 5-9-5V7l9-5Zm0 10 9-5M12 12 3 7m9 5v10M7 4l10 5"
        />
      </symbol>
      <symbol id="file" viewBox="0 0 24 24">
        <path d="M5 2h9l5 5v15H5V2Zm9 0v6h5M8 13h8m-8 4h6" />
      </symbol>
      <symbol id="code" viewBox="0 0 24 24">
        <path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18" />
      </symbol>
      <symbol id="spark" viewBox="0 0 24 24">
        <path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z" />
      </symbol>
    </svg>
    <nav class="topbar" aria-label="Main navigation">
      <a class="brand" href="./"
        ><span class="brand-mark"
          ><svg><use href="#layers" /></svg></span
        ><span>CAESAR<small>ISOMETRIC WORKSPACE</small></span></a
      >
      <div class="topbar-right">
        <span class="workspace-pill"><i></i>Engineering workspace</span
        ><a class="back-link" href="./"
          >Open workspace <svg><use href="#external" /></svg
        ></a>
      </div>
    </nav>
    <main class="content">
      <header class="heading">
        <div>
          <span class="eyebrow">YOUR ENGINEERING WORKSPACE</span>
          <h1>Pick up where you left off.</h1>
          <p>Your drawings, decisions, and lessons. All in one place.</p>
        </div>
        <a class="back-link" href="./"
          >All projects <svg><use href="#external" /></svg
        ></a>
      </header>
      <section class="loader-card" aria-labelledby="loader-title">
        <div class="loader-main">
          <div>
            <div class="loader-icon">
              <svg><use href="#folder" /></svg>
            </div>
            <h2 id="loader-title">Load a project</h2>
            <p class="loader-description">
              Open your working drawings directly in the website.
            </p>
            <div class="project-controls">
              <select id="project" aria-label="Select a project" disabled>
                <option>Loading your projects…</option></select
              ><button class="button" id="load-project" disabled>
                Load project <svg><use href="#arrow" /></svg>
              </button>
            </div>
            <p id="status" class="status" role="status"></p>
            <button class="button" id="sign-in" hidden>
              Enter local workspace <svg><use href="#arrow" /></svg>
            </button>
            <p class="subtext">
              <svg><use href="#shield" /></svg>Source PDFs stay intact.
              Engineering edits stay traceable.
            </p>
            <div class="hosting-panel">
              <h3><svg aria-hidden="true"><use href="#box" /></svg>Set up your own hosting</h3>
              <p>Download the application with the website already built, then follow the cPanel setup steps.</p>
              <div class="hosting-actions">
                <a class="button" id="download-system" href="https://github.com/efrgdgr0024345/stress/raw/refs/heads/main/downloads/caesar-cpanel.zip">
                  <svg aria-hidden="true"><use href="#download" /></svg>Download cPanel ZIP
                </a>
                <button class="button secondary" id="install-cpanel" aria-expanded="false" aria-controls="cpanel-guide">
                  <svg aria-hidden="true"><use href="#code" /></svg>Install on cPanel
                </button>
              </div>
              <p>Requires Python 3.12, Passenger Python support and dependency installation access. PHP-only hosting cannot run the complete system.</p>
              <div class="install-guide" id="cpanel-guide" hidden>
                <h3>cPanel installation guide</h3>
                <p>These steps configure your hosting account. This page does not connect to cPanel or install files automatically.</p>
                <ol>
                  <li>Download the ZIP. In cPanel File Manager, upload and extract it in your home directory, outside <code>public_html</code>. It creates <code>caesar-system/</code>.</li>
                  <li>In <strong>Setup Python App</strong>, select Python 3.12, application root <code>caesar-system</code>, startup file <code>passenger_wsgi.py</code>, and entry point <code>application</code>. You can use a domain root or a path such as <code>https://easyai.com.au/stress/</code>. Keep the application root outside <code>public_html</code>; the public URL is routed to Python by Passenger. Never expose the application source directory as a public document root.</li>
                  <li>Activate the virtual environment using the command supplied by cPanel. In the application directory run:
                    <pre><code>python -m pip install --upgrade pip
python -m pip install -r requirements-cpanel.txt
python scripts/check_host.py</code></pre>
                    Or use cPanel's dependency installer with <code>requirements-cpanel.txt</code>. Node.js is not needed on your hosting.</li>
                  <li>From the application directory, run <code>python scripts/configure_cpanel.py</code>. It prompts for your email and a hidden password, and saves configuration in an account-private file outside the website. Alternatively configure the <code>CAESAR_*</code> environment variables described in <code>docs/CPANEL.md</code>.</li>
                  <li>Restart the Python application in cPanel. For a <code>/stress/</code> installation, visit <code>https://easyai.com.au/stress/api/v1/health</code> and confirm <code>mode: authenticated</code>. Open <code>/stress/</code>, sign in, create a project, and test a non-sensitive PDF upload and export.</li>
                </ol>
                <p class="hosting-note"><strong>Private pilot:</strong> keep the complete application URL, including its API, behind your provider's access restriction or VPN. Upload isolation, rate limiting and other production security work remain. The ZIP includes <code>docs/CPANEL.md</code> with verification, backup and troubleshooting steps.</p>
              </div>
            </div>
          </div>
          <aside class="loader-info">
            <svg><use href="#branch" /></svg>
            <h3>The drawing is your workspace.</h3>
            <p>
              View every sheet, place nodes, edit annotations, review evidence,
              and export — all from your browser.
            </p>
            <div class="info-tags">
              <span>IN-BROWSER EDITING</span><span>NATIVE PDF EXPORT</span>
            </div>
          </aside>
        </div>
      </section>
      <!-- The lessons register is deliberately immediately below the Load project section. -->
      <section aria-labelledby="lessons-title">
        <div class="lessons-heading">
          <div>
            <div>
              <h2 id="lessons-title">
                Lessons learned <span class="count" id="lesson-count">…</span>
              </h2>
              <p>What we’ve learned. What we’ll carry forward.</p>
            </div>
          </div>
          <a
            class="github-link"
            href="https://github.com/efrgdgr0024345/stress/blob/main/LESSONS_LEARNED.md"
            target="_blank"
            rel="noopener noreferrer"
            >View on GitHub <svg><use href="#external" /></svg
          ></a>
        </div>
        <div id="lessons" class="lessons-grid" aria-live="polite">
          <div class="empty loading">Loading the lessons register…</div>
        </div>
      </section>
      <footer class="footer">
        <span
          ><svg><use href="#shield" /></svg>Graphic positions never establish
          physical dimensions.</span
        ><span>CAESAR ISO · Engineering review workspace</span>
      </footer>
    </main>
    <script>
      (() => {
        "use strict";
        const byId = (id) => document.getElementById(id);
        const base = new URL(".", window.location.href).pathname;
        byId("install-cpanel").addEventListener("click", () => {
          const guide = byId("cpanel-guide");
          guide.hidden = !guide.hidden;
          byId("install-cpanel").setAttribute("aria-expanded", String(!guide.hidden));
        });
        // The GitHub link also works when this loader is copied to a PHP host.
        fetch(base + "downloads/caesar-cpanel.zip", { method: "HEAD" })
          .then((response) => {
            if (response.ok && response.headers.get("content-type")?.includes("application/zip")) {
              byId("download-system").href = base + "downloads/caesar-cpanel.zip";
              byId("download-system").download = "caesar-cpanel.zip";
            }
          }).catch(() => {});
        const palettes = [
          ["#007aff", "#eaf3ff", "shield"],
          ["#af52de", "#f5edfb", "box"],
          ["#ff9500", "#fff4e5", "file"],
          ["#30a46c", "#eaf8f0", "branch"],
          ["#5856d6", "#efefff", "code"],
          ["#ff6b67", "#fff0ef", "shield"],
          ["#32a8b8", "#eaf8fa", "layers"],
          ["#ba8c45", "#fcf5e8", "book"],
        ];
        function icon(name) {
          const svg = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "svg",
          );
          svg.setAttribute("aria-hidden", "true");
          const use = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "use",
          );
          use.setAttribute("href", "#" + name);
          svg.append(use);
          return svg;
        }
        function el(tag, cls, text) {
          const node = document.createElement(tag);
          if (cls) node.className = cls;
          if (text !== undefined) node.textContent = text;
          return node;
        }
        function showLessons(items) {
          const root = byId("lessons");
          root.replaceChildren();
          byId("lesson-count").textContent = String(items.length);
          if (!items.length) {
            root.append(
              el("div", "empty", "No lessons have been recorded yet."),
            );
            return;
          }
          items.forEach((lesson, index) => {
            const [accent, tint, glyph] = palettes[index % palettes.length],
              card = el("article", "lesson");
            card.style.setProperty("--accent", accent);
            card.style.setProperty("--tint", tint);
            const top = el("div", "lesson-top"),
              badge = el("span", "lesson-icon");
            badge.append(icon(glyph));
            const meta = el("div", "lesson-meta");
            meta.append(
              el("span", "", lesson.id),
              el("small", "", lesson.category || "Project learning"),
            );
            const adopted = el("span", "adopted");
            adopted.append(
              icon("check"),
              document.createTextNode(lesson.status || "Recorded"),
            );
            top.append(badge, meta, adopted);
            const action = el("div", "lesson-action"),
              actionText = el("div");
            actionText.append(
              el("b", "", "What we do next"),
              el("p", "", lesson.action || ""),
            );
            action.append(icon("arrow"), actionText);
            const evidence = el("details"),
              summary = el("summary");
            summary.append(
              icon("file"),
              document.createTextNode("Evidence & context"),
            );
            evidence.append(
              summary,
              el("p", "", lesson.evidence || "See the shared register."),
            );
            card.append(
              top,
              el("h3", "", lesson.title),
              el("p", "lesson-body", lesson.lesson || ""),
              action,
              evidence,
            );
            root.append(card);
          });
        }
        function parseLessons(text) {
          return [
            ...text.matchAll(
              /^## (LESSON-\d+[^\n]*)\n([\s\S]*?)(?=^## |$(?![\s\S]))/gm,
            ),
          ].map((match) => {
            const lesson = {
              id: match[1].split(" ")[0],
              title: match[1].split("—").slice(1).join("—").trim(),
            };
            for (const field of match[2].matchAll(
              /^- (Category|Status|Lesson|Action|Evidence): (.+)$/gm,
            ))
              lesson[field[1].toLowerCase()] = field[2];
            return lesson;
          });
        }
        async function request(path, options) {
          const response = await fetch(base + "api/v1" + path, {
            credentials: "same-origin",
            ...options,
          });
          if (!response.ok) {
            const error = new Error("The workspace service is unavailable.");
            error.status = response.status;
            throw error;
          }
          return response.json();
        }
        async function lessons() {
          try {
            showLessons((await request("/lessons")).lessons);
          } catch {
            try {
              const response = await fetch("LESSONS_LEARNED.md");
              if (!response.ok) throw new Error();
              showLessons(parseLessons(await response.text()));
            } catch {
              byId("lessons").replaceChildren(
                el(
                  "div",
                  "empty",
                  "Sign in to the workspace to read the shared lessons register.",
                ),
              );
              byId("lesson-count").textContent = "—";
            }
          }
        }
        async function load() {
          try {
            const projects = await request("/projects"),
              select = byId("project");
            select.replaceChildren();
            if (!projects.length) {
              select.append(
                new Option("No projects yet — create one in the workspace", ""),
              );
              byId("status").textContent =
                "Create a project in the workspace, then return here to load it.";
              return;
            }
            projects.forEach((p) =>
              select.append(new Option(p.title + " · " + p.line_id, p.id)),
            );
            select.disabled = false;
            byId("load-project").disabled = false;
            byId("status").textContent =
              projects.length +
              " project" +
              (projects.length === 1 ? "" : "s") +
              " available. Drawings open in the browser workspace.";
            byId("sign-in").hidden = true;
            await lessons();
          } catch (error) {
            byId("status").classList.add("error");
            byId("project").replaceChildren(
              new Option("Sign in to choose your project", ""),
            );
            if (error.status === 401) {
              byId("status").textContent =
                "Sign in to load your private project drawings.";
              try {
                const health = await request("/health");
                if (health.mode === "local-development")
                  byId("sign-in").hidden = false;
                else
                  byId("status").append(
                    document.createTextNode(" "),
                    Object.assign(el("a", "", "Open sign-in"), {
                      href: base + "?returnTo=loader",
                    }),
                  );
              } catch {}
            } else
              byId("status").textContent =
                "Connect this loader to the CAESAR workspace service to load projects. The lessons register remains available below.";
            await lessons();
          }
        }
        byId("load-project").addEventListener("click", () => {
          const id = byId("project").value;
          if (id)
            window.location.assign(
              base + "?project=" + encodeURIComponent(id) + "&view=workspace",
            );
        });
        byId("sign-in").addEventListener("click", async () => {
          byId("sign-in").disabled = true;
          try {
            await request("/auth/local", { method: "POST" });
            byId("status").classList.remove("error");
            await load();
          } catch {
            byId("status").textContent =
              "Sign-in failed. Open the workspace to sign in.";
          } finally {
            byId("sign-in").disabled = false;
          }
        });
        load();
      })();
    </script>
  </body>
</html>
