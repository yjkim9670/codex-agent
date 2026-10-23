// Verify the dashboard with deterministic data, without starting or touching a Workbench server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium, expect} = require('@playwright/test');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, 'codex-web-app', file), 'utf8');
const template = read('templates/usage_dashboard.html').replace(/<link[^>]*>/g, '').replace(/<script[^>]*><\/script>/g, '');
const qualified = (groups, value) => ({groups, tokens:1000000, pp_per_million_tokens:value});
const report = {
    start:'2026-08-30T00:00:00+09:00', end:'2026-10-05T12:00:00+09:00',
    collected_at:'2026-10-05T12:00:00+09:00', limits_observed_at:null,
    effort:'all', efforts:['medium','low'], accounts:{accounts:[]}, environments:[],
    total_tokens:1000, current_limits:{},
    daily:{'2026-10-05':{alpha:400},'2026-08-30':{alpha:100},'2026-09-01':{beta:300},'2026-08-31':{alpha:200}},
    models:{alpha:{total_tokens:700},beta:{total_tokens:300}},
    model_efforts:{'alpha/medium':{model:'alpha',reasoning_effort:'medium',total_tokens:500},'alpha/low':{model:'alpha',reasoning_effort:'low',total_tokens:200},'beta/medium':{model:'beta',reasoning_effort:'medium',total_tokens:300}},
    windows:{
        five_hour:{model_efforts:{'alpha/medium':qualified(3,1.25),'alpha/low':qualified(2,99),'beta/medium':qualified(4,null)},groups:[],excluded:{}},
        weekly:{model_efforts:{'alpha/medium':qualified(2,77),'alpha/low':qualified(3,.5)},groups:[],excluded:{}}
    },
    quota_samples:[{limits_observed_at:'2026-09-01T01:00:00+09:00',five_hour_used_percent:20,five_hour_resets_at:'a'}, {limits_observed_at:'2026-09-02T01:00:00+09:00',five_hour_used_percent:10,five_hour_resets_at:'b'}],
    collection_diagnostics:{},sources:[],collection_errors:[],reconciliation:{daily:[],comparable_days:0,comparable_difference_tokens:0,account_missing_days:0}
};
if(process.argv.includes('--serve')) {
    const http=require('node:http');
    const staticRoot=path.join(root,'codex-web-app/static');
    const html=read('templates/usage_dashboard.html')
        .replace(/\{\{ url_for\('static', filename='([^']+)', v=\d+\) \}\}/g, '/static/$1');
    const server=http.createServer((req,res)=>{
        const pathname=new URL(req.url,'http://localhost').pathname;
        if(pathname==='/api/codex/usage/dashboard') {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(report));return;}
        if(pathname.startsWith('/static/')) {
            const file=path.resolve(staticRoot,pathname.slice(8));
            if(!file.startsWith(staticRoot+path.sep) || !fs.existsSync(file)) {res.writeHead(404);res.end();return;}
            res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'font/woff2');
            res.end(fs.readFileSync(file));return;
        }
        res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);
    });
    server.listen(0,'127.0.0.1',()=>console.log(`Fixture server http://127.0.0.1:${server.address().port}/usage`));
} else (async()=>{
    const browser = await chromium.launch({headless:true});
    try {
        const page = await browser.newPage({viewport:{width:1440,height:1000},timezoneId:'America/Los_Angeles'});
        const errors=[], requests=[];
        let empty=false, fail=false;
        page.on('pageerror', e=>errors.push(e.message));
        await page.route('http://usage.test/**', route=>{
            if (route.request().url().includes('/api/')) {
                requests.push(new URL(route.request().url()));
                if(fail) return route.fulfill({status:500,json:{error:'fixture error'}});
                const data=structuredClone(report);
                if(empty) Object.assign(data,{daily:{},models:{},model_efforts:{},quota_samples:[],total_tokens:0});
                return route.fulfill({json:data});
            }
            return route.fulfill({contentType:'text/html',body:template});
        });
        await page.goto('http://usage.test/usage');
        await page.addStyleTag({content:read('static/css/usage_dashboard.css')});
        await page.addScriptTag({content:read('static/js/usage_dashboard.js')});
        await expect(page.locator('#usage-dashboard')).toHaveAttribute('data-loaded','true');
        assert.equal(requests[0].searchParams.get('effort'),'all');
        assert.equal(requests[0].searchParams.get('days'),'90');
        await expect(page.locator('#model-rows tr')).toHaveCount(3);
        await expect(page.locator('#comparison .bar-row')).toHaveCount(1);
        await expect(page.locator('#comparison')).toContainText('1.250');
        assert.deepEqual(await page.locator('#monthly-rows tr td:nth-child(2)').allTextContents(),['400','300','300']);
        assert.deepEqual(await page.locator('#weekly-rows tr td:nth-child(2)').allTextContents(),['400','0','0','0','0','500','100']);
        await expect(page.locator('#weekly-rows tr').first()).toContainText('2026-10-05 주');
        await expect(page.locator('#monthly-rows tr').last()).toContainText('일부 기간');
        await expect(page.locator('#monthly-rows tr').nth(1)).not.toContainText('일부 기간');
        await expect(page.locator('#model-rows tr').filter({hasText:'alpha / low'}).locator('td').nth(3)).toHaveText('—');
        await page.locator('[data-window="weekly"]').click();
        await expect(page.locator('#comparison .bar-row')).toHaveCount(1);
        await expect(page.locator('#comparison')).toContainText('low');
        await expect(page.locator('#comparison')).toContainText('0.500');
        const geometry = () => page.locator('.chart svg').evaluateAll(nodes=>nodes.map(el=>({width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height})));
        await expect(page.locator('#token-chart svg')).not.toContainText('0.0M');
        const baseline=await geometry();
        const zoomButton=(id,action)=>page.locator(`[data-chart="${id}"][data-zoom="${action}"]`);
        await zoomButton('token-chart','in').click();
        let enlarged=await geometry();
        enlarged.forEach((item,i)=>{assert.equal(item.height,baseline[i].height);if(i===2) assert(item.width>baseline[i].width);else assert.equal(item.width,baseline[i].width);});
        await zoomButton('token-chart','in').click(); await zoomButton('token-chart','in').click();
        await expect(zoomButton('token-chart','in')).toBeDisabled();
        await expect(page.locator('#token-chart-zoom-level')).toHaveText('8×');
        await zoomButton('quota-chart','in').click();
        await expect(page.locator('#quota-chart-zoom-level')).toHaveText('2×');
        await expect(page.locator('#token-chart-zoom-level')).toHaveText('8×');
        await page.locator('#refresh').click();
        await expect(page.locator('#status')).toContainText('수집');
        await expect(page.locator('#token-chart-zoom-level')).toHaveText('8×');
        // Chart totals and order match the calendar tables (charts run oldest to newest).
        assert.deepEqual(await page.locator('#monthly-chart .period-bar').evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.tokens))),[300,300,400]);
        assert.deepEqual(await page.locator('#weekly-chart .period-bar').evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.tokens))),[100,500,0,0,0,0,400]);
        for(const id of ['token-chart','quota-chart','monthly-chart','weekly-chart']) {
            await zoomButton(id,'reset').click();
            const plot=page.locator(`#${id} svg`);
            await plot.hover({position:{x:100,y:75}});
            const tip=page.locator(`#${id} .chart-tooltip`);
            await expect(tip).toBeVisible();
            await expect(page.locator(`#${id} .chart-crosshair`)).toHaveAttribute('visibility','visible');
            assert(Math.abs(Number(await page.locator(`#${id} .chart-crosshair`).getAttribute('x1'))-100)<1);
            await expect(tip).toContainText(id==='quota-chart' ? '10%' : '토큰');
            const tipBox=await tip.boundingBox(), hostBox=await page.locator(`#${id}`).boundingBox();
            assert(tipBox.x>=hostBox.x && tipBox.x+tipBox.width<=hostBox.x+hostBox.width+1);
            await page.locator('h1').hover();
            await expect(tip).toBeHidden();
            await page.locator(`#${id} .chart-scroll`).focus();
            await page.keyboard.press('ArrowRight');
            await expect(tip).toBeVisible();
            await page.keyboard.press('Escape');
            await expect(tip).toBeHidden();
            await zoomButton(id,'in').click();
            await expect(page.locator(`#${id}-zoom-level`)).toHaveText('2×');
            await zoomButton(id,'out').click();
            await expect(page.locator(`#${id}-zoom-level`)).toHaveText('1×');
        }
        await zoomButton('token-chart','in').click();
        // At every viewport only the chart/table regions may overflow horizontally.
        for(const width of [320,390,768,1440]) {
            await page.setViewportSize({width,height:900});
            await page.waitForTimeout(80);
            assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`page overflow at ${width}`);
            assert.equal(await page.locator('.model-details .table-wrap').evaluate(el=>getComputedStyle(el).maxHeight),'none');
            const scroller=page.locator('#token-chart .chart-scroll');
            await scroller.focus();
            await page.keyboard.press('ArrowLeft');
            for(let i=0;i<37;i++) await page.keyboard.press('ArrowRight');
            await page.waitForTimeout(100);
            assert(await scroller.evaluate(el=>el.scrollLeft>0));
        }
        await page.setViewportSize({width:1440,height:1000});
        await page.waitForTimeout(80);
        await zoomButton('token-chart','reset').click();
        await expect(zoomButton('token-chart','out')).toBeDisabled();
        assert.deepEqual(await geometry(),baseline);
        // A failed refresh must recover without a stale warning style.
        fail=true; await page.locator('#refresh').click();
        await expect(page.locator('#status')).toHaveClass('warning');
        fail=false; empty=true; await page.locator('#refresh').click();
        await expect(page.locator('#status')).not.toHaveClass('warning');
        await expect(page.locator('#model-rows tr')).toHaveCount(0);
        await expect(page.locator('#comparison .empty')).toBeVisible();
        await expect(page.locator('#monthly-rows tr td:nth-child(2)').first()).toHaveText('0');
        await page.locator('#quota-chart svg').hover({position:{x:100,y:75}});
        await expect(page.locator('#quota-chart .chart-tooltip')).toBeHidden();
        assert.deepEqual(errors,[]);
        console.log('Usage dashboard: calendar totals, reliability, full list, independent scope, hover overlays, period charts, responsive layout and recovery passed.');
    } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
