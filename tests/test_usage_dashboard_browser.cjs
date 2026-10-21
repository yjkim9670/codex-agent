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
(async()=>{
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
        await page.locator('#zoom-in').click();
        let enlarged=await geometry();
        enlarged.forEach((item,i)=>{assert(item.width>baseline[i].width);assert.equal(item.height,baseline[i].height);});
        await page.locator('#zoom-in').click(); await page.locator('#zoom-in').click();
        await expect(page.locator('#zoom-in')).toBeDisabled();
        await expect(page.locator('#zoom-level')).toHaveText('8×');
        await page.locator('#refresh').click();
        await expect(page.locator('#status')).toContainText('수집');
        await expect(page.locator('#zoom-level')).toHaveText('8×');
        // At every viewport only the chart/table regions may overflow horizontally.
        for(const width of [320,390,768,1440]) {
            await page.setViewportSize({width,height:900});
            await page.waitForTimeout(80);
            assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`page overflow at ${width}`);
            assert.equal(await page.locator('.model-details .table-wrap').evaluate(el=>getComputedStyle(el).maxHeight),'none');
            const scroller=page.locator('#token-chart .chart-scroll');
            await scroller.focus();
            await page.keyboard.press('ArrowRight');
            await page.waitForTimeout(100);
            assert(await scroller.evaluate(el=>el.scrollLeft>0));
        }
        await page.setViewportSize({width:390,height:900});
        await page.waitForTimeout(80);
        await page.screenshot({path:path.join(root,'.agent_state/usage-dashboard-mobile-review.png'),fullPage:true});
        await page.setViewportSize({width:1440,height:1000});
        await page.waitForTimeout(80);
        await page.locator('#zoom-reset').click();
        await expect(page.locator('#zoom-out')).toBeDisabled();
        assert.deepEqual(await geometry(),baseline);
        await page.screenshot({path:path.join(root,'.agent_state/usage-dashboard-review.png'),fullPage:true});
        // A failed refresh must recover without a stale warning style.
        fail=true; await page.locator('#refresh').click();
        await expect(page.locator('#status')).toHaveClass('warning');
        fail=false; empty=true; await page.locator('#refresh').click();
        await expect(page.locator('#status')).not.toHaveClass('warning');
        await expect(page.locator('#model-rows tr')).toHaveCount(0);
        await expect(page.locator('#comparison .empty')).toBeVisible();
        await expect(page.locator('#monthly-rows tr td:nth-child(2)').first()).toHaveText('0');
        assert.deepEqual(errors,[]);
        console.log('Usage dashboard: calendar totals, reliability, full list, horizontal zoom, responsive layout and recovery passed.');
    } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
