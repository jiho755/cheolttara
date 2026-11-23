import sys, subprocess, time, json
from playwright.sync_api import sync_playwright
import os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=os.path.join(ROOT,'screens')+'/'
os.makedirs(OUT,exist_ok=True)
BASE='http://localhost:8765/'
srv=subprocess.Popen(['python3','-m','http.server','8765','-d',ROOT],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(1)
results=[]
def check(name,cond,extra=''):
    results.append((name,bool(cond),extra)); print(('PASS' if cond else 'FAIL'),name,extra)
try:
  with sync_playwright() as p:
    b=p.chromium.launch()
    for date in ['2026-04-05','2026-07-20','2026-11-23']:
        ctx=b.new_context(viewport={'width':390,'height':844},device_scale_factor=2,locale='ko-KR')
        ctx.grant_permissions(['notifications'])
        pg=ctx.new_page(); errs=[]
        pg.on('console',lambda m,e=errs: e.append(m.text) if m.type=='error' else None)
        pg.on('pageerror',lambda x,e=errs: e.append(str(x)))
        url=f'{BASE}?date={date}'
        pg.goto(url); pg.wait_for_selector('body[data-ready="1"]')
        tag=date
        n=pg.locator('#view .card').count()
        check(f'{tag} home items render',n>0,f'{n} cards')
        pg.screenshot(path=OUT+f'{tag}_1home.png')
        # filter
        pg.click('[data-filter=food]'); nf=pg.locator('#view .card').count()
        check(f'{tag} food filter',0<nf<=n,f'{nf}')
        pg.click('[data-filter=all]')
        # pick first in-season item
        first=pg.locator('#view .card[data-open]').first
        iid=first.get_attribute('data-open'); 
        first.click(); pg.wait_for_selector('.sheet')
        check(f'{tag} detail sheet tip',pg.locator('.tipbox').count()==1)
        pg.wait_for_timeout(400); pg.screenshot(path=OUT+f'{tag}_2detail.png')
        pg.click('#sheetHeart'); pg.click('#sheetClose')
        # also heart on 2nd card
        h2=pg.locator('#view [data-heart]').nth(1); h2.click()
        # bucket
        pg.click('[data-tab=bucket]')
        nb=pg.locator('#view .card').count()
        check(f'{tag} bucket has 2',nb==2,str(nb))
        pg.screenshot(path=OUT+f'{tag}_3bucket.png')
        pg.click(f'[data-done="{iid}"]'); pg.wait_for_selector('#doneSave')
        pg.fill('#memoIn','맛있었다 '+'가'*60)
        v=pg.input_value('#memoIn'); check(f'{tag} memo max 50',len(v)==50,str(len(v)))
        pg.wait_for_timeout(400); pg.screenshot(path=OUT+f'{tag}_4donesheet.png')
        pg.click('#doneSave'); pg.wait_for_selector('.stampline')
        check(f'{tag} done stamp shown',pg.locator(f'[data-undo="{iid}"]').count()==1)
        pg.screenshot(path=OUT+f'{tag}_5bucket_done.png')
        # reload persistence
        pg.goto(url); pg.wait_for_selector('body[data-ready="1"]'); pg.click('[data-tab=bucket]')
        check(f'{tag} persists after reload',pg.locator(f'[data-undo="{iid}"]').count()==1 and pg.locator('#view .card').count()==2)
        # stamps
        pg.click('[data-tab=stamps]')
        check(f'{tag} 4 boards',pg.locator('.board').count()==4)
        on=pg.locator('.stamp.on').count(); check(f'{tag} stamp on board',on==1,str(on))
        progs=pg.locator('.prog').all_inner_texts(); print('  ',progs)
        check(f'{tag} progress format',all('/' in t for t in progs) and any(t.split()[1].startswith('1/') for t in progs))
        total=sum(int(t.split('/')[1]) for t in progs); check(f'{tag} boards cover 100',total==100,str(total))
        pg.screenshot(path=OUT+f'{tag}_6stamps.png'); pg.evaluate('window.scrollTo(0,900)'); pg.screenshot(path=OUT+f'{tag}_6stamps_scrolled.png'); pg.evaluate('window.scrollTo(0,0)')
        pg.click('#makeCard'); pg.wait_for_selector('#cardOut[data-ready="1"]')
        info=pg.evaluate("()=>{const c=document.querySelector('#cardOut');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let nb=0;for(let i=0;i<d.length;i+=4*97){if(d[i]!==251||d[i+1]!==248)nb++}return [c.width,c.height,nb]}")
        check(f'{tag} share card 1080x1350 drawn',info[0]==1080 and info[1]==1350 and info[2]>50,str(info))
        # export card png via canvas
        data=pg.evaluate("()=>document.querySelector('#cardOut').toDataURL('image/png')")
        import base64; open(OUT+f'{tag}_7card.png','wb').write(base64.b64decode(data.split(',')[1]))
        with pg.expect_download() as dl: pg.click('#cardShare')
        check(f'{tag} card download fallback',dl.value.suggested_filename.endswith('.png'))
        pg.click('#cardClose')
        # alerts
        pg.click('[data-tab=alerts]')
        pg.screenshot(path=OUT+f'{tag}_8alerts.png')
        na=pg.locator('.alert').count(); print('  alerts',na, pg.locator('.alert').all_inner_texts())
        check(f'{tag} alerts note',pg.locator('#notifyNote').inner_text().find('백그라운드')>=0)
        pg.click('#notifySwitch'); pg.wait_for_timeout(500)
        check(f'{tag} notify denied -> stays off',pg.get_attribute('#notifySwitch','aria-checked')=='false')
        pg.click('[data-tab=home]')
        # undo
        pg.click('[data-tab=bucket]'); pg.click(f'[data-undo="{iid}"]')
        check(f'{tag} undo works',pg.locator(f'[data-done="{iid}"]').count()==1)
        check(f'{tag} no console errors',not errs,str(errs))
        ctx.close()
    # photo flow + soon section on one date
    ctx=b.new_context(viewport={'width':390,'height':844},locale='ko-KR'); pg=ctx.new_page(); errs=[]
    pg.on('console',lambda m: errs.append(m.text) if m.type=='error' else None); pg.on('pageerror',lambda x: errs.append(str(x)))
    from PIL import Image
    Image.new('RGB',(2400,1600),(200,120,90)).save('/tmp/big.jpg')
    pg.goto(BASE+'?date=2026-04-05'); pg.wait_for_selector('body[data-ready="1"]')
    check('soon section present (04-05)',pg.locator('h2:has-text("곧 시작해요")').count()==1)
    check('곧 끝나요 badge exists',pg.locator('.badge.end').count()>0)
    pg.locator('#view [data-heart]').first.click(); pg.click('[data-tab=bucket]')
    pg.locator('[data-done]').first.click(); pg.set_input_files('#photoIn','/tmp/big.jpg'); pg.wait_for_selector('#photoPrev:not([hidden])')
    pg.click('#doneSave'); pg.wait_for_selector('.stampline img')
    dims=pg.evaluate("async()=>{const r=await new Promise(res=>{const q=indexedDB.open('cheolttara');q.onsuccess=()=>{const g=q.result.transaction('records').objectStore('records').getAll();g.onsuccess=()=>res(g.result)}});const bm=await createImageBitmap(r[0].photo);return [bm.width,bm.height,r[0].photo.type]}")
    check('photo resized <=1000 JPEG',max(dims[:2])==1000 and dims[2]=='image/jpeg',str(dims))
    pg.click('[data-tab=stamps]'); pg.click('#makeCard'); pg.wait_for_selector('#cardOut[data-ready="1"]'); pg.wait_for_timeout(300)
    data=pg.evaluate("()=>document.querySelector('#cardOut').toDataURL('image/png')"); open(OUT+'photo_card.png','wb').write(base64.b64decode(data.split(',')[1]))
    pg.screenshot(path=OUT+'photo_flow.png')
    # offline SW
    pg.wait_for_timeout(1000); pg.reload(); pg.wait_for_timeout(800)
    ctx.set_offline(True)
    try:
        pg.goto(BASE+'?date=2026-04-05',timeout=8000); pg.wait_for_selector('body[data-ready="1"]',timeout=8000)
        check('offline load via SW',pg.locator('#view .card').count()>0)
    except Exception as e: check('offline load via SW',False,str(e)[:100])
    check('no console errors (photo/offline flow)',not errs,str(errs))
    # notification flow with stubbed permission
    ctx=b.new_context(viewport={'width':390,'height':844},locale='ko-KR'); pg=ctx.new_page(); errs=[]
    pg.on('pageerror',lambda x: errs.append(str(x)))
    pg.add_init_script('''
      window.__notes=JSON.parse(sessionStorage.getItem('n')||'[]');
      const rec=(t,o)=>{window.__notes.push([t,o&&o.tag]);sessionStorage.setItem('n',JSON.stringify(window.__notes))};
      function N(t,o){rec(t,o)} N.permission='default'; N.requestPermission=async()=>{N.permission='granted';return 'granted'};
      window.Notification=N;
      if(window.ServiceWorkerRegistration) ServiceWorkerRegistration.prototype.showNotification=async function(t,o){rec(t,o)};
    ''')
    u=BASE+'?date=2026-04-05'
    pg.goto(u); pg.wait_for_selector('body[data-ready="1"]')
    # bucket 개나리 (ends D-5) via detail
    pg.click('[data-filter=nature]')
    pg.locator('[data-open="nature-forsythia"]').click() if pg.locator('[data-open="nature-forsythia"]').count() else pg.locator('#view .card[data-open]').first.click()
    pg.click('#sheetHeart'); pg.click('#sheetClose')
    pg.click('[data-tab=alerts]'); pg.click('#notifySwitch'); pg.wait_for_timeout(800)
    check('notify toggle on (stub granted)',pg.get_attribute('#notifySwitch','aria-checked')=='true')
    n1=pg.evaluate('window.__notes.length'); check('notification shown on enable',n1>=1,str(pg.evaluate('window.__notes')))
    pg.goto(u); pg.wait_for_selector('body[data-ready="1"]'); pg.wait_for_timeout(500)
    n2=pg.evaluate('window.__notes.length'); check('at most once per item per day',n2==n1,f'{n1}->{n2}')
    check('no page errors (notify flow)',not errs,str(errs))
    b.close()
finally:
    srv.terminate()
print('FAILS:',[r[0] for r in results if not r[1]])
