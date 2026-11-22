"""Browser controls with a fake provider boundary; no account or billable call."""
import json
from playwright.sync_api import expect


def exercise_connections(page, base):
    state = {'configured': False, 'runner_ready': True, 'demo': {}}
    sentinel = 'dop_v1_BROWSER_PRIVATE_TEST_SENTINEL_1234567890'
    def handle(route):
        if route.request.method == 'POST':
            assert route.request.post_data_json == {'token': sentinel}
            state['configured'] = True
        elif route.request.method == 'DELETE':
            state['configured'] = False
        route.fulfill(status=200, content_type='application/json', body=json.dumps(state))
    page.route('**/api/v1/system/digitalocean', handle)
    try:
        page.get_by_role('button', name='Admin connections', exact=True).click()
        expect(page.get_by_role('heading', name='Connections.')).to_be_visible()
        expect(page.get_by_text('Not connected', exact=True)).to_be_visible()
        page.get_by_label('Personal access token', exact=True).fill(sentinel)
        page.get_by_role('button', name='Save & test connection', exact=True).click()
        expect(page.get_by_text('Connected', exact=True)).to_be_visible()
        expect(page.get_by_label('Replace access token', exact=True)).to_have_value('')
        expect(page.get_by_role('button', name='Deploy & test worker', exact=True)).to_be_disabled()
        assert sentinel not in page.locator('body').inner_text()
        page.reload()
        expect(page.get_by_role('heading', name='Connections.')).to_be_visible()
        expect(page.get_by_label('Replace access token', exact=True)).to_have_value('')
        assert page.evaluate('Object.values(localStorage).some(v => v.includes("BROWSER_PRIVATE_TEST_SENTINEL"))') is False
        page.screenshot(path='/tmp/caesar-screens/admin-connections.png', full_page=True)
        page.get_by_role('button', name='Remove saved token', exact=True).click()
        expect(page.get_by_text('Not connected', exact=True)).to_be_visible()
        page.get_by_role('button', name='Projects', exact=True).click()
        expect(page.get_by_role('heading', name='Projects.')).to_be_visible()
    finally:
        page.unroute('**/api/v1/system/digitalocean', handle)
