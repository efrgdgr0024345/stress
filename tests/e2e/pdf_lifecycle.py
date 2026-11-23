"""Delayed source/preview fetches can be cancelled; real HTTP failures stay visible."""
from playwright.sync_api import expect
from tests.e2e.real_drawing import wait_for_drawing


def exercise_pdf_lifecycle(page,context,base):
    project=next(p for p in context.request.get(base+'/api/v1/projects').json() if p['line_id']=='CONTINUATION-QA-001')
    page.goto(base+f"/?project={project['id']}&view=results",wait_until='domcontentloaded')
    page.evaluate("""() => {
      const original=window.fetch.bind(window);
      window.pdfLifecycle={hold:true,pending:0,aborts:0,fail:false};
      window.fetch=(url,options={})=>{
        const state=window.pdfLifecycle;
        if (!/\\/sources\\/|\\/artifacts\\/[^/]+\\/pdf(?:$|[?])/.test(String(url))) return original(url,options);
        if (state.fail) return Promise.resolve(new Response('Unavailable',{status:503}));
        if (!state.hold) return original(url,options);
        state.pending++;
        return new Promise((resolve,reject)=>{
          const abort=()=>{state.aborts++;reject(new DOMException('Cancelled by navigation','AbortError'));};
          if(options.signal?.aborted) abort();
          else options.signal?.addEventListener('abort',abort,{once:true});
        });
      };
    }""")
    page.locator('.sidebar').get_by_role('button',name='Drawing workspace',exact=True).click()
    page.wait_for_function('window.pdfLifecycle.pending===1')
    page.get_by_label('Next sheet',exact=True).click()
    page.wait_for_function('window.pdfLifecycle.pending===2 && window.pdfLifecycle.aborts===1')
    page.locator('.sidebar').get_by_role('button',name='Excel results',exact=True).click()
    page.wait_for_function('window.pdfLifecycle.aborts===2')
    page.evaluate('window.pdfLifecycle.hold=false;window.pdfLifecycle.fail=true')
    page.locator('.sidebar').get_by_role('button',name='Drawing workspace',exact=True).click()
    expect(page.get_by_text('PDF preview could not load:',exact=False)).to_contain_text('HTTP 503')
    page.locator('.sidebar').get_by_role('button',name='Excel results',exact=True).click()
    page.evaluate('window.pdfLifecycle.fail=false')
    page.locator('.sidebar').get_by_role('button',name='Drawing workspace',exact=True).click()
    wait_for_drawing(page,'.paper canvas')
    page.locator('.sidebar').get_by_role('button',name='Project flow',exact=True).click()
    expect(page.get_by_role('button',name='Preview PDF',exact=True)).to_be_visible(timeout=30000)
    page.evaluate('window.pdfLifecycle.hold=true')
    page.get_by_role('button',name='Preview PDF',exact=True).click()
    page.wait_for_function('window.pdfLifecycle.pending===3')
    page.get_by_role('button',name='Close dialog',exact=True).click()
    page.wait_for_function('window.pdfLifecycle.aborts===3')
    page.evaluate('window.pdfLifecycle.hold=false')
    page.get_by_role('button',name='Preview PDF',exact=True).click()
    wait_for_drawing(page,'.pdf-preview canvas')
    page.get_by_role('button',name='Close dialog',exact=True).click()
    print('PASS: cancelled delayed source and preview loads, rapid sheet/view changes, visible HTTP failure and successful PDF reopen.',flush=True)
