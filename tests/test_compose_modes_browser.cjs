// Isolated browser check using the current template, stylesheet and mode functions.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium, expect } = require('@playwright/test');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'codex-web-app/static/js/app.js'), 'utf8');
const template = fs.readFileSync(path.join(root, 'codex-web-app/templates/index.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'codex-web-app/static/css/app.css'), 'utf8');
const slice = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));

(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--use-mock-keychain'] });
    try {
        const page = await browser.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        const formStart = template.indexOf('<form id="codex-chat-form"');
        const form = template.slice(formStart, template.indexOf('</form>', formStart) + 7);
        await page.setContent(`<style>${css}</style><main style="display:flex;flex-direction:column;justify-content:flex-end;min-height:100dvh">${form}</main>`);
        await page.addScriptTag({ content: `
            const state = { settings: { planModeState: 'off' } };
            ${slice('const PLAN_MODE_STATE_OFF =', 'let hasManualTheme')}
            ${slice('function normalizePlanModeState(', 'function getChatToolsOverlayElements(')}
            ${slice('function setPlanModeToggleState(', 'function getExecutionPolicyPreset(')}
            ${slice('function getComposeModelRole(', "document.getElementById('codex-execution-settings-save')")}
            document.getElementById('codex-chat-input').addEventListener('keydown', cyclePlanModeFromKeyboardEvent);
            for (const button of [document.getElementById('codex-plan-mode-toggle'), document.querySelector('[data-chat-compose-action="plan"]')]) {
                button.addEventListener('click', () => openComposeModeMenu(button));
                button.addEventListener('keydown', cyclePlanModeFromKeyboardEvent);
            }
            document.getElementById('codex-chat-compose-tools-toggle').addEventListener('click', () => {
                document.getElementById('codex-chat-compose-tools-menu').classList.remove('is-hidden');
            });
            setupComposeModeMenu();
            setPlanModeToggleState('off');
        ` });
        await require('./playwright/compose-modes.cjs').verifyComposeModes(page, expect);
        const settingsStart = template.indexOf('<div class="ui-settings-overlay" id="codex-ui-settings-overlay"');
        const settings = template.slice(settingsStart, template.indexOf('<div class="branch-overlay"', settingsStart)).replace(/{%[\s\S]*?%}/g, '');
        let layoutChecks = 0;
        for (const [width, height] of [[360, 360], [600, 360], [820, 600], [1280, 800], [1920, 1080]]) {
            for (const scale of [0.8, 0.9, 1.1]) {
                await page.setViewportSize({ width, height });
                await page.setContent(`<style>${css}</style>${settings}`);
                const geometry = await page.evaluate(({ scale, height }) => {
                    document.documentElement.style.setProperty('--ui-scale', scale);
                    document.documentElement.classList.toggle('is-short-overlay-viewport', height < 560);
                    document.getElementById('codex-ui-settings-overlay').classList.add('is-visible');
                    const card = document.querySelector('#codex-ui-settings-overlay .ui-settings-card');
                    const body = card.querySelector('.ui-settings-body');
                    const header = card.querySelector('.ui-settings-header');
                    const footer = card.querySelector('.ui-settings-footer');
                    const groups = [...body.querySelectorAll('.workbench-settings-group')];
                    body.scrollTop = body.scrollHeight;
                    const bounds = card.getBoundingClientRect();
                    return {
                        left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom, width: bounds.width,
                        columns: getComputedStyle(body).gridTemplateColumns.split(' ').length,
                        overflow: body.scrollWidth - body.clientWidth,
                        headerBottom: header.getBoundingClientRect().bottom,
                        bodyTop: body.getBoundingClientRect().top,
                        bodyBottom: body.getBoundingClientRect().bottom,
                        footerTop: footer.getBoundingClientRect().top,
                        groupEnds: groups.map(group => group.lastElementChild.getBoundingClientRect().bottom),
                    };
                }, { scale, height });
                const message = JSON.stringify({ width, height, scale, geometry });
                assert.ok(geometry.left >= -1 && geometry.right <= width + 1, message);
                assert.ok(geometry.top >= -1 && geometry.bottom <= height + 1, message);
                assert.ok(geometry.overflow <= 1, message);
                assert.ok(geometry.headerBottom <= geometry.bodyTop + 1, message);
                assert.ok(geometry.footerTop >= geometry.bodyBottom - 1, message);
                assert.ok(geometry.groupEnds.every(bottom => bottom <= geometry.bodyBottom + 1), message);
                if (width >= 1280) {
                    assert.equal(geometry.columns, 2, message);
                    assert.ok(geometry.width > 700, message);
                }
                if (width <= 600) assert.equal(geometry.columns, 1, message);
                layoutChecks++;
            }
        }
        console.log(`PASS: ${layoutChecks} settings layout cases, responsive columns, UI scaling and scroll reachability`);
        assert.deepEqual(errors, []);
        console.log('PASS: Chromium click/Shift+Tab, roles, mobile synchronization and label layout at 1280×800, 600×360, 360×360');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
