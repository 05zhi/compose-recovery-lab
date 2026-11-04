"""Actual Chromium UI login/search/download, isolated from host and Internet."""
import hashlib,os
from pathlib import Path
from playwright.sync_api import sync_playwright

def browser_smoke():
    folder=Path('/tmp/evidence');folder.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
        context=browser.new_context(accept_downloads=True,record_video_dir=str(folder),viewport={'width':1280,'height':720})
        page=context.new_page()
        try:
            page.goto('http://127.0.0.1:8080/',wait_until='domcontentloaded')
            page.locator('#password').fill(os.environ['DEMO_PASSWORD'])
            page.get_by_role('button',name='Sign in',exact=True).click()
            page.locator('#search').wait_for(state='visible')
            page.get_by_role('button',name='Search',exact=True).click()
            page.get_by_text('6 items',exact=True).wait_for()
            with page.expect_download() as event:
                page.get_by_role('button',name='Download',exact=True).first.click()
            download=event.value
            assert not download.failure()
            content=Path(download.path()).read_bytes()
            assert hashlib.sha256(content).hexdigest()==hashlib.sha256(b'Inventory synthetic specification SKU-01\n').hexdigest()
            with page.expect_download() as export_event:
                page.get_by_role('button',name='Export CSV',exact=True).click()
            assert Path(export_event.value.path()).read_text(encoding='utf-8')=='sku,quantity\n'+''.join(f'SKU-{i:02},{i*15}\n' for i in range(1,7))
        finally:
            video=page.video
            context.close()
            video.save_as(str(folder/'browser.webm'))
            browser.close()

if __name__=='__main__':browser_smoke()
