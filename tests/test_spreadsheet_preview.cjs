// Run: PLAYWRIGHT_BROWSERS_PATH=./.playwright-browsers node tests/test_spreadsheet_preview.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('@playwright/test');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'codex-web-app/static/js/app.js'), 'utf8');
const helpers = source.slice(source.indexOf('function formatSpreadsheetColumnLabel('), source.indexOf('function renderNativePdfPreviewIntoContainer('));
const XLSX = require('../codex-web-app/static/vendor/xlsx-0.18.5.full.min.js');
const workbook = XLSX.utils.book_new();
const sheet = XLSX.utils.aoa_to_sheet([
    ['병합 제목', null, '금액', '날짜'],
    ['긴 내용 <script>alert(1)</script>\n두 번째 줄', 0.125, 1234.5, 45292],
    ['마지막', 0, false, '끝'],
]);
sheet.B2.z = '0.0%'; sheet.C2.z = '#,##0.00'; sheet.D2.z = 'yyyy-mm-dd';
sheet['!merges'] = [XLSX.utils.decode_range('A1:B1')];
sheet['!cols'] = [{ wpx: 220 }, { wpx: 85 }, { wpx: 110 }, { wpx: 120 }];
sheet['!rows'] = [{ hpt: 36 }, { hpt: 45 }];
XLSX.utils.book_append_sheet(workbook, sheet, '서식 시트');
XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([['다른 시트']]), '두 번째');
// Exercise the real bundled reader, then supply presentation XML as an XLSX producer would.
const buffer = XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' });
(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--use-mock-keychain'] });
    try {
        for (const theme of ['light', 'dark']) for (const width of [390, 1280]) {
            const page = await browser.newPage({ viewport: { width, height: 800 } });
            await page.setContent(`<html data-theme="${theme}"><head></head><body><main id="preview"></main></body></html>`);
            await page.addStyleTag({ path: path.join(root, 'codex-web-app/static/css/app.css') });
            await page.addStyleTag({ content: ':root { --ui-scale: 1; }' });
            await page.addScriptTag({ path: path.join(root, 'codex-web-app/static/vendor/xlsx-0.18.5.full.min.js') });
            await page.addScriptTag({ content: `
                const FILE_BROWSER_SPREADSHEET_MAX_ROWS = 200, FILE_BROWSER_SPREADSHEET_MAX_COLS = 50,
                    FILE_BROWSER_SPREADSHEET_MAX_SHEETS = 25, FILE_BROWSER_SPREADSHEET_ROW_HEADER_WIDTH_PX = 60,
                    FILE_BROWSER_SPREADSHEET_COLUMN_WIDTH_PX = 144;
                async function writeTextToClipboard(text) { window.copied = text; }
                function getCodexAppStylesheetUrl() { return 'data:text/css,'; }
                ${helpers}
            ` });
            await page.evaluate(bytes => {
                const wb = XLSX.read(new Uint8Array(bytes), { type: 'array', cellStyles: true, cellNF: true, bookFiles: true });
                const xml = `<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                  <fonts><font><name val="Arial"/><sz val="11"/><color rgb="FF123456"/><b/><i/><u/></font></fonts>
                  <fills><fill><patternFill patternType="solid"><fgColor rgb="FFFFCC00"/></patternFill></fill></fills>
                  <borders><border><bottom style="medium"><color rgb="FFCC0000"/></bottom></border></borders>
                  <cellXfs><xf fontId="0" fillId="0" borderId="0"><alignment horizontal="center" vertical="center" wrapText="1"/></xf></cellXfs>
                </styleSheet>`;
                wb.files['xl/styles.xml'].content = new TextEncoder().encode(xml);
                document.querySelector('#preview').append(buildSpreadsheetPreview(wb, XLSX));
                window.testWorkbook = wb;
            }, Array.from(buffer));
            const active = page.locator('.file-browser-spreadsheet-sheet.is-active');
            const title = active.locator('td[data-address="A1"]');
            assert.equal(await title.getAttribute('colspan'), '2');
            assert.equal(await active.locator('td[data-address="B1"]').count(), 0);
            const style = await title.evaluate(el => {
                const s = getComputedStyle(el);
                return { color: s.color, background: s.backgroundColor, weight: s.fontWeight, align: s.textAlign,
                    vertical: s.verticalAlign, bottom: s.borderBottomWidth, row: el.parentElement.getBoundingClientRect().height,
                    width: el.getBoundingClientRect().width };
            });
            assert.equal(style.color, 'rgb(18, 52, 86)');
            assert.equal(style.background, 'rgb(255, 204, 0)');
            assert.equal(style.weight, '700'); assert.equal(style.align, 'center');
            assert.equal(style.vertical, 'middle'); assert.equal(style.bottom, '2px');
            assert.ok(style.row >= 48); assert.ok(style.width > 290 && style.width < 325);
            assert.equal(await active.locator('td[data-address="B2"]').innerText(), '12.5%');
            assert.equal(await active.locator('td[data-address="C2"]').innerText(), '1,234.50');
            assert.equal(await active.locator('td[data-address="D2"]').innerText(), '2024-01-01');
            await title.click();
            await page.keyboard.press('ArrowDown');
            const text = active.locator('textarea');
            assert.equal(await text.inputValue(), '긴 내용 <script>alert(1)</script>\n두 번째 줄');
            assert.equal(await active.locator('td script').count(), 0);
            await active.getByRole('button', { name: '셀 복사', exact: true }).click();
            assert.equal(await page.evaluate(() => window.copied), await text.inputValue());
            assert.equal(await active.locator('[role="status"]').innerText(), '복사했습니다.');
            await active.locator('td[data-address="A2"]').focus();
            assert.equal(await page.evaluate(() => {
                const event = new Event('copy', { bubbles: true, cancelable: true });
                const clipboard = new DataTransfer();
                Object.defineProperty(event, 'clipboardData', { value: clipboard });
                document.activeElement.dispatchEvent(event);
                return clipboard.getData('text/plain');
            }), await text.inputValue());
            await page.getByRole('tab', { name: '두 번째', exact: true }).click();
            assert.equal(await active.locator('td').innerText(), '다른 시트');
            assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
            await page.getByRole('tab', { name: '서식 시트', exact: true }).click();
            assert.ok(await active.locator('.file-browser-spreadsheet-grid').evaluate(el => el.scrollWidth > el.clientWidth || window.innerWidth > 1000));
            if (theme === 'light' && width === 1280) {
                const popupReady = page.waitForEvent('popup');
                await page.evaluate(() => document.querySelector('.file-browser-spreadsheet').openSpreadsheetPreview());
                const popup = await popupReady;
                await popup.addStyleTag({ path: path.join(root, 'codex-web-app/static/css/app.css') });
                const popupSheet = popup.locator('.file-browser-spreadsheet-sheet.is-active');
                await popupSheet.locator('td[data-address="B2"]').click();
                assert.equal(await popupSheet.locator('textarea').inputValue(), '12.5%');
                await popupSheet.getByRole('button', { name: '셀 복사', exact: true }).click();
                assert.equal(await page.evaluate(() => window.copied), '12.5%');
                await popup.getByRole('tab', { name: '두 번째', exact: true }).click();
                assert.equal(await popupSheet.locator('td').innerText(), '다른 시트');
                assert.equal(await popup.evaluate(() => window.opener), null);
                await popup.close();
            }
            await page.close();
        }
        // Non-A1 range, merges clipped by the preview limit, empty and legacy workbooks.
        const page = await browser.newPage();
        await page.addScriptTag({ content: `const FILE_BROWSER_SPREADSHEET_MAX_ROWS=2, FILE_BROWSER_SPREADSHEET_MAX_COLS=2,
            FILE_BROWSER_SPREADSHEET_MAX_SHEETS=25, FILE_BROWSER_SPREADSHEET_ROW_HEADER_WIDTH_PX=60,
            FILE_BROWSER_SPREADSHEET_COLUMN_WIDTH_PX=144; ${helpers}` });
        await page.addScriptTag({ path: path.join(root, 'codex-web-app/static/vendor/xlsx-0.18.5.full.min.js') });
        const edge = await page.evaluate(() => {
            const sheet = { '!ref': 'C3:F8', '!merges': [XLSX.utils.decode_range('C3:E6')], C3: { t:'s', v:'clip' } };
            const view = buildSpreadsheetPreview({ SheetNames:['clip', 'empty'], Sheets:{clip:sheet, empty:{}} }, XLSX);
            document.body.append(view);
            const cell = view.querySelector('td');
            return { rows:cell.rowSpan, cols:cell.colSpan, address:cell.dataset.address,
                count:view.querySelectorAll('td').length, text:view.textContent,
                empty:buildSpreadsheetPreview({ SheetNames:[] }, XLSX).textContent };
        });
        assert.equal(edge.rows, 2); assert.equal(edge.cols, 2); assert.equal(edge.address, 'C3'); assert.equal(edge.count, 1);
        assert.match(edge.text, /최대 2행/); assert.match(edge.text, /표시할 데이터가 없습니다/);
        assert.match(edge.text, /일부 원본 서식/); assert.match(edge.empty, /표시할 시트가 없습니다/);
        console.log('PASS: spreadsheet styles, merges, dimensions, formats, selection, keyboard, copy, tabs, escaping, limits; light/dark × desktop/mobile');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
