from playwright.async_api import async_playwright


class BaseScraper:
    def __init__(self, headless=True):
        self.pw = None
        self.browser = None
        self.page = None
        self.headless = headless

    async def start(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=self.headless)
        self.page = await self.browser.new_page()

    async def quit(self):
        if self.pw:
            await self.pw.stop()
        if self.browser:
            await self.browser.close()
        if self.page:
            await self.page.close()
