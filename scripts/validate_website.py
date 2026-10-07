"""Browser integration check: actual login, WAV/MP3 uploads and saved alert details."""
from pathlib import Path
import json
import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.runtime'/'validation'
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://localhost:3000/dang-nhap.html')
    page.locator('#email').fill('admin@gmail.com')
    page.locator('#password').fill('password123')
    page.locator('#login-btn').click()
    page.wait_for_url('**/tong-quan.html')
    page.goto('http://localhost:3000/canh-bao.html')
    checks=[]
    for name in ['normal.wav','help.mp3']:
        page.locator('#audio-upload').set_input_files(str(OUT/name))
        page.locator('#dialog-modal').wait_for(state='visible',timeout=180000)
        content=page.locator('#dialog-modal-body').inner_text()
        assert 'TRANSCRIPT' in content and 'SỰ KIỆN ÂM THANH' in content and 'AI PHÂN TÍCH' in content
        assert '00:' in content
        assert 'đánh' in content.lower() if name=='help.mp3' else 'Xin chào' in content
        assert 'chính xác 95' not in content
        audio=page.locator('#dialog-modal-body audio').get_attribute('src')
        assert audio and audio.startswith('/uploads/')
        page.screenshot(path=str(OUT/('website-'+name+'.png')))
        checks.append(dict(file=name,sections_rendered=True,transcript_and_timestamps=True,audio_url=audio))
        page.evaluate("document.getElementById('dialog-modal').style.display='none'")
    page.goto('http://localhost:3000/lich-su.html')
    page.wait_for_function("document.querySelectorAll('#history-tbody tr[onclick]').length > 0")
    page.locator('#history-tbody tr[onclick]').first.click()
    page.locator('#detail-modal.active').wait_for(state='visible')
    assert 'TRANSCRIPT' in page.locator('#modal-body').inner_text()
    page.screenshot(path=str(OUT/'website-history.png'))
    checks.append(dict(history_saved_transcript=True))
    page.evaluate("document.getElementById('detail-modal').classList.remove('active')")
    page.locator('#audio-analysis-history [data-analysis-id]').first.wait_for()
    page.locator('#audio-analysis-history [data-analysis-id]').first.click()
    page.locator('#detail-modal.active').wait_for(state='visible')
    assert 'AI PHÂN TÍCH' in page.locator('#modal-body').inner_text()
    checks.append(dict(all_audio_analysis_history_accessible=True))
    # Compile every project script with the browser's JS parser without executing it.
    for source in (ROOT/'frontend').glob('*.js'):
        page.evaluate('(source) => {new Function(source)}',source.read_text(encoding='utf-8'))
    checks.append(dict(all_frontend_js_syntax_valid=True,page_errors=errors))
    (OUT/'website-results.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
if errors:
    raise RuntimeError('Browser errors: '+str(errors))
print(json.dumps(checks,ensure_ascii=False),flush=True)
