const path = require('path');

module.exports = {
    testDir: path.resolve(__dirname, '..', 'tests', 'playwright'),
    testMatch: 'browser-smoke.spec.cjs',
    fullyParallel: false,
    forbidOnly: true,
    workers: 1,
    retries: 0,
    reporter: 'line',
    use: {
        browserName: 'chromium',
        headless: true,
        screenshot: 'only-on-failure',
        trace: 'off',
        video: 'off',
        launchOptions: {
            args: ['--use-mock-keychain'],
        },
    },
};
