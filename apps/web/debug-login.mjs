/* global console */
import { chromium } from '@playwright/test';
const browser = await chromium.launch({executablePath:'/usr/bin/google-chrome', headless:true});
const page = await browser.newPage({baseURL:'http://localhost:3000'});
page.on('console', msg => console.log('CONSOLE', msg.type(), msg.text()));
page.on('pageerror', err => console.log('PAGEERROR', err.message));
page.on('request', req => { if (req.url().includes('/api/v1/')) console.log('REQ', req.method(), req.url()); });
page.on('response', async res => { if (res.url().includes('/api/v1/')) console.log('RES', res.status(), res.url()); });
async function fulfillJson(route, json, status=200) { await route.fulfill({status, contentType:'application/json', body: JSON.stringify(json)}); }
await page.route('**/api/v1/auth/login', async route => { console.log('ROUTE login'); await fulfillJson(route, {access_token:'mock-access-token',refresh_token:'mock-refresh-token',expires_in:900,user:{id:'4d1b0f76-a961-4f8d-8bcb-3f7d5f530001',email:'alex@musematic.dev',display_name:'Alex Mercer',avatar_url:null,roles:['workspace_admin','agent_operator','analytics_viewer'],workspace_id:'workspace-1',mfa_enrolled:true}}); });
await page.route('**/api/v1/auth/oauth/providers', async route => { console.log('ROUTE oauth providers'); await fulfillJson(route, {providers:[]}); });
await page.route('**/api/v1/workspaces/*/analytics/summary', async route => { await fulfillJson(route, {workspace_id:'workspace-1',active_agents:1,active_agents_change:0,running_executions:0,running_executions_change:0,pending_approvals:0,pending_approvals_change:0,cost_current:1,cost_previous:1,period_label:'Apr 2026'}); });
await page.route('**/api/v1/workspaces/*/dashboard/recent-activity', async route => { await fulfillJson(route, {workspace_id:'workspace-1',items:[]}); });
await page.route('**/api/v1/workspaces/*/dashboard/pending-actions', async route => { await fulfillJson(route, {workspace_id:'workspace-1',total:0,items:[]}); });
await page.goto('http://localhost:3000/login');
console.log('URL after goto', page.url());
await page.getByLabel('Email').fill('alex@musematic.dev');
await page.getByLabel('Password').fill('SecretPass1!');
await page.getByRole('button', {name:/sign in/i}).click();
await page.waitForTimeout(3000);
console.log('URL after click', page.url());
console.log('BODY', await page.locator('body').innerText());
await browser.close();
