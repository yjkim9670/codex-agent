# Workbench Chat design verification

Result: passed in local headless Chromium with touch/viewport emulation.

## Scope

Verified the selected design in `conversation-app/templates/index.html`,
`conversation-app/static/css/selected-design.css` and `conversation-app/static/js/chat.js`.
Used the existing isolated Flask fixture with real Web Crypto, encrypted requests,
SQLite and streamed deterministic model responses. Production conversations and
accounts were not changed. No operational server was restarted.

The earlier IAB/consent blocker is resolved by the user's explicit local browser
verification instructions. The project deterministic runner was used. `design.md`
is absent; this is a rendered review of the existing selected design, not a pixel
comparison against the historical source image.

## Screen coverage

CSS viewport dimensions, not physical device pixels. Each mobile/tablet/fold size
was checked in both portrait and landscape. Desktop sizes use their listed dimensions.

| Surface | Base viewport | Coverage |
| --- | --- | --- |
| Small mobile | 360 × 780 | Both orientations |
| Mobile | 390 × 844 | Both orientations |
| Large mobile | 412 × 915 | Both orientations |
| Narrow fold cover | 344 × 882 | Both orientations |
| Fold cover | 374 × 904 | Both orientations |
| Fold inner | 768 × 900 | Both orientations |
| Wide fold inner | 853 × 1010 | Both orientations |
| Tablet split width | 600 × 960 | Both orientations |
| Tablet | 820 × 1180 | Both orientations |
| Large tablet | 1024 × 1366 | Both orientations |
| Desktop | 1440 × 900 | Desktop |
| Wide desktop | 1920 × 1080 | Desktop |
| Original reference dimensions | 1487 × 1058 | Desktop |

23 viewport/orientation combinations; 46 individual light/dark screenshots saved
and reviewed through contact sheets, with representative mobile/fold/desktop
captures inspected at larger size. Additional checks cover 110% UI scale, short
360px-high viewport simulation, and cover-to-inner transitions preserving drafts.

Artifacts (local, Git ignored):

- `.agent_state/ui-verification/responsive-results.json`: measured geometry.
- `.agent_state/ui-verification/index.html`: screenshot gallery.
- `.agent_state/ui-verification/contact-sheet-light.jpg` and `contact-sheet-dark.jpg`.
- `.agent_state/ui-verification/*-portrait*.png` and `*-landscape*.png`.
  Desktop screenshots retain the test's `portrait` case label; their actual dimensions
  are the landscape desktop sizes listed above.

## Findings fixed

- Mobile header buttons inherited excess padding/line height: header measured
  63.3px and failed the existing compact-header regression. Reduced mobile header
  button padding and line height. Recheck measured 51px header, 108px composer,
  621px reading area at 360 × 780; 301px reading area at 360 × 460.
- Touch devices were excluded from Enter submission. Removed the pointer/width
  restriction; Enter submits, Shift+Enter remains a newline, IME composition and
  keyCode 229 remain protected. Checked with touch-emulated browser keyboard events.
- Bumped CSS/JS asset query versions for the fixes.

## Checks completed

- Responsive geometry: no document horizontal overflow, composer inside the visual
  viewport, send beside the textarea, usable reading region, contained settings
  dialogs/drawers, drawer Escape/focus restoration, desktop collapse/restore,
  rotation/folding draft preservation, light/dark theme and 110% UI scale.
- Existing sidebar suite: scrollable history and long titles, desktop physical width
  independent of scale, loading/error/missing usage values preserve layout geometry,
  mobile account details, hidden search reset and session selection.
- Existing conversation suites: resume, overlays/backdrop/inert/focus, short viewport,
  encrypted POST/SSE/poll fallback, timeout/recovery, cancel, Markdown/code/table/XSS,
  all eight fonts, theme, clipboard, usage/reset timestamps and refresh failures.
- Long output: 151 messages, 60k live characters and 100 updates completed with zero
  repeated Markdown parses (observed 260.4ms; diagnostic measurement, not a benchmark).
- Backend/transport: 36 tests passed.
- JavaScript syntax and `git diff --check`: passed.

Initial browser run passed sidebar and all 23 responsive combinations, then failed
at the compact-header assertion. After fixing the actual CSS defect, reran the five
affected mobile/cover surfaces with the new explicit compact-header assertion and
the previously incomplete conversation suites. They passed. Unaffected passing
sidebar/tablet/desktop responsive checks were not rerun.

Reproduce with an isolated fixture:

```sh
python3.14 tests/serve_conversation_fixture.py --port 0
# Use the printed loopback URL in a second shell:
CODEX_VERIFY_CONVERSATION_RESPONSIVE=1 CODEX_VERIFY_CONVERSATION_SIDEBAR=1 CODEX_VERIFY_CONVERSATION=1 python3.14 scripts/verify_browser_ui.py --url <URL> --selector '#composer' --output-dir .agent_state/ui-verification/failures
python3.14 -m pytest tests/test_conversation_backend.py tests/test_conversation_transport.py -q
```

Do not point the fixture-dependent suites at production: they create test conversations.

## Deployment state and limits

Read-only HTTP check of the running `http://127.0.0.1:3101/` returned 200 but still
referenced `selected-design.css?v=1` and `chat.js?v=17`; current source references v2
and v18. The running Flask process has cached its template. The user needs to restart
Proc Manager's **Workbench Chat - conversation server** and reload clients to pick
up the current asset versions. This verification used the current canonical source
on a separate temporary loopback server, which was stopped after checks.

No physical iPad/iPhone/Fold device or Safari/WebKit was exercised. Touch emulation
and short viewport resizing do not prove native virtual-keyboard, safe-area, hinge,
or operating-system behavior. Browser-emulated coverage is complete for the matrix
above; real-device validation remains outside the evidence collected here.
