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
        // Only for the loopback fixture's ephemeral self-signed certificate.
        ignoreHTTPSErrors: process.env.CODEX_VERIFY_LOCAL_TLS === '1',
        screenshot: 'only-on-failure',
        trace: 'off',
        video: 'off',
        launchOptions: {
            args: ['--use-mock-keychain'],
        },
    },
};
