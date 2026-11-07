// Shared modal in standalone Chat, including its real encrypted upload path.
exports.verifyConversationVoice = async (page, expect) => {
    await page.evaluate(() => {
        window.originalVoiceRequest = window.workbenchVoice.request;
        window.originalRecorder = window.MediaRecorder;
        window.voiceTracks = [];
        window.workbenchVoice.request = async (path, options = {}) => {
            if (options.method === 'POST') {
                if (!window.voiceRetried) { window.voiceRetried = true; throw new Error('일시적 전사 실패'); }
                return {ok:true, json:async () => ({id:'fixture'})};
            }
            if (path.endsWith('/fixture')) return {ok:true, json:async () => ({state:'done', text:'음성 결과'})};
            return window.originalVoiceRequest(path, options);
        };
        Object.defineProperty(navigator, 'mediaDevices', {configurable:true, value:{
            getUserMedia: async () => {
                const track = {stopped:false, stop(){this.stopped=true;}};
                window.voiceTracks.push(track);
                return {getTracks:() => [track]};
            }
        }});
        window.MediaRecorder = class {
            static isTypeSupported(){return true;}
            constructor(){this.state='inactive';}
            start(){this.state='recording';}
            stop(){this.state='inactive';setTimeout(()=>{this.ondataavailable({data:new Blob(['audio'])});this.onstop();},20);}
        };
    });
    const input = page.locator('#message'), panel = page.locator('#voice-panel');
    const start = page.locator('#voice-start'), stop = page.locator('#voice-stop');
    await page.setViewportSize({width:390, height:844});
    await input.fill('기존 초안');
    await input.evaluate(el => el.setSelectionRange(el.value.length, el.value.length));
    await start.click(); await expect(stop).toBeVisible();
    expect(await panel.evaluate(el => el.matches(':modal'))).toBe(true);
    const box = await panel.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x+box.width).toBeLessThanOrEqual(390);
    await page.keyboard.press('Tab'); expect(await panel.evaluate(el => el.contains(document.activeElement))).toBe(true);
    await stop.click();
    await expect(page.locator('#voice-retry')).toBeVisible();
    await expect(page.locator('#voice-download')).toBeVisible();
    await page.locator('#voice-retry').click();
    await expect(page.locator('#voice-result')).toHaveValue('음성 결과');
    await expect(input).toHaveValue('기존 초안');
    await page.locator('#voice-insert').click();
    await expect(panel).toBeHidden(); await expect(input).toHaveValue('기존 초안음성 결과');
    await start.click(); await expect(stop).toBeVisible(); await page.keyboard.press('Escape');
    await expect(panel).toBeHidden(); await expect(start).toBeFocused();
    expect(await page.evaluate(() => window.voiceTracks.every(track => track.stopped))).toBe(true);
    // Native recorder sends generated silence through ChatTransport to real local tools.
    await page.evaluate(() => {
        window.workbenchVoice.request = window.originalVoiceRequest;
        window.MediaRecorder = window.originalRecorder;
        navigator.mediaDevices.getUserMedia = async () => {
            const context = new AudioContext(), dest = context.createMediaStreamDestination();
            const source = context.createOscillator(), volume = context.createGain();
            volume.gain.value=0; source.connect(volume).connect(dest);source.start();await context.resume();
            window.voiceContext=context; window.voiceStream=dest.stream; return dest.stream;
        };
    });
    await start.click(); await expect(stop).toBeVisible();
    await page.waitForTimeout(1100); await stop.click();
    await expect(page.locator('#voice-status')).toContainText('전사 결과를 확인한 후', {timeout:60000});
    expect(await page.evaluate(() => window.voiceStream.getTracks().every(track=>track.readyState==='ended'))).toBe(true);
    await page.locator('#voice-cancel').click(); await page.evaluate(() => window.voiceContext.close());
};
