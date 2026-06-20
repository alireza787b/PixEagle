const { defineConfig, devices } = require('@playwright/test');

const baseURL = process.env.PIXEAGLE_E2E_BASE_URL;
const publicHost = process.env.PIXEAGLE_E2E_PUBLIC_HOST || 'pixeagle.test';
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined;

if (!baseURL) {
  throw new Error('PIXEAGLE_E2E_BASE_URL is required');
}
if (process.env.PIXEAGLE_E2E_ALLOW_SELF_SIGNED_TLS !== '1') {
  throw new Error('PIXEAGLE_E2E_ALLOW_SELF_SIGNED_TLS=1 is required');
}

module.exports = defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [['line']],
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    screenshot: 'off',
    trace: 'off',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium-production-remote',
      use: {
        ...devices['Desktop Chrome'],
        browserName: 'chromium',
        launchOptions: {
          executablePath,
          args: [
            `--host-resolver-rules=MAP ${publicHost} 127.0.0.1,EXCLUDE localhost`,
          ],
        },
      },
    },
  ],
});
