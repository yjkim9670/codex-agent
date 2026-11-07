// Runs in the project's deterministic runner against an isolated local server.
exports.verifyVoice = async (page, expect) => {
    const config = await page.request.get(new URL('/api/codex/voice', page.url()).href);
    expect(config.ok()).toBe(true);
    expect((await config.json()).error).toBeNull();
    expect(config.headers()['cache-control']).toBe('no-store');
    await page.evaluate(() => {
        window.nativeRecorder = window.MediaRecorder;
        window.voiceTracks = [];
        window.voiceRecorders = [];
        Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: {
            getUserMedia: async () => {
                const track = {stopped: false, stop() {this.stopped = true;}};
                window.voiceTracks.push(track);
                return {getTracks: () => [track]};
            },
        }});
        window.MediaRecorder = class {
            static isTypeSupported() {return true;}
            constructor() {this.state = 'inactive'; window.voiceRecorders.push(this);}
            start() {this.state = 'recording';}
            stop() {
                this.state = 'inactive';
                setTimeout(() => {
                    this.ondataavailable({data: new Blob(['audio'])});
                    this.onstop();
                }, 20);
            }
        };
    });
    const input = page.locator('#codex-chat-input');
    const start = page.locator('#voice-start');
    const stop = page.locator('#voice-stop');
    const cancel = page.locator('#voice-cancel');
    const status = page.locator('#voice-status');
    const result = page.locator('#voice-result');
    let latePoll;
    let delayPoll = false;
    await page.route('**/api/codex/voice', async route => {
        if (route.request().method() === 'POST') {
            expect(route.request().headers()['x-codex-csrf-token']).toBeTruthy();
            await route.fulfill({status: 202, json: {id: 'voice-fixture'}});
        }
        else await route.continue();
    });
    await page.route('**/api/codex/voice/voice-fixture', async route => {
        if (route.request().method() === 'DELETE') {
            expect(route.request().headers()['x-codex-csrf-token']).toBeTruthy();
            await route.fulfill({status: 204});
        }
        else if (delayPoll) latePoll = route;
        else await route.fulfill({json: {state: 'done', text: '음성 결과'}});
    });
    await input.fill('기존 초안');
    await input.evaluate(el => el.setSelectionRange(el.value.length, el.value.length));
    await start.click(); await expect(stop).toBeVisible();
    expect(await page.locator('#voice-panel').evaluate(el => el.matches(':modal'))).toBe(true);
    await stop.click();
    await expect(result).toHaveValue('음성 결과');
    await expect(input).toHaveValue('기존 초안');
    await page.locator('#voice-insert').click();
    await expect(input).toHaveValue('기존 초안음성 결과');
    expect(await page.evaluate(() => window.voiceTracks.every(track => track.stopped))).toBe(true);

    // A poll response received after cancellation must not replace new state.
    delayPoll = true;
    await start.click(); await expect(stop).toBeVisible(); await stop.click();
    await expect.poll(() => Boolean(latePoll)).toBe(true);
    await cancel.click();
    await start.click(); await expect(stop).toBeVisible();
    await latePoll.fulfill({json: {state: 'done', text: '취소된 결과'}});
    await expect(result).toBeHidden();
    await expect(stop).toBeVisible();
    await cancel.click();
    await expect(page.locator('#voice-panel')).toBeHidden();
    expect(await page.evaluate(() => window.voiceTracks.every(track => track.stopped))).toBe(true);

    await start.click(); await expect(stop).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('#voice-panel')).toBeHidden();
    await expect(start).toBeFocused();
    expect(await page.evaluate(() => window.voiceTracks.every(track => track.stopped))).toBe(true);

    // Native MediaRecorder -> real upload -> ffmpeg -> real model, using
    // generated silence without access to a user's microphone.
    await page.unroute('**/api/codex/voice');
    await page.unroute('**/api/codex/voice/voice-fixture');
    await page.evaluate(() => {
        window.MediaRecorder = window.nativeRecorder;
        navigator.mediaDevices.getUserMedia = async () => {
            const context = new AudioContext();
            const destination = context.createMediaStreamDestination();
            const source = context.createOscillator();
            const volume = context.createGain();
            volume.gain.value = 0;
            source.connect(volume).connect(destination);
            source.start();
            await context.resume();
            window.voiceContext = context;
            window.voiceStream = destination.stream;
            return destination.stream;
        };
    });
    await start.click(); await expect(stop).toBeVisible();
    await page.waitForTimeout(1100);
    const upload = page.waitForResponse(response => response.url().endsWith('/api/codex/voice') && response.request().method() === 'POST');
    await stop.click();
    const uploadResponse = await upload;
    expect(uploadResponse.request().headers()['x-codex-csrf-token']).toBeTruthy();
    expect(uploadResponse.status()).toBe(202);
    await expect(status).toContainText('전사 결과를 확인한 후', {timeout: 60_000});
    await expect(input).toHaveValue('기존 초안음성 결과');
    expect(await page.evaluate(() => window.voiceStream.getTracks().every(track => track.readyState === 'ended'))).toBe(true);
    await cancel.click();
    await page.evaluate(() => window.voiceContext.close());
    await expect(page.locator('#voice-panel')).toBeHidden();
};
