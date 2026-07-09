import { test, expect } from '@playwright/test';

test.describe('Search Page', () => {
  test('page loads with correct title', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/GitHub Stars/);
  });

  test('loading screen disappears after init', async ({ page }) => {
    await page.goto('/');
    const loadingScreen = page.locator('#loadingScreen');
    await expect(loadingScreen).toHaveClass(/hidden/, { timeout: 120000 });
  });

  test('search input is visible', async ({ page }) => {
    await page.goto('/');
    await page.locator('#searchInput').waitFor({ state: 'visible', timeout: 60000 });
    await expect(page.locator('#searchInput')).toBeVisible();
  });

  test('index status updates after worker ready', async ({ page }) => {
    await page.goto('/');
    const indexStatus = page.locator('#indexStatus');
    await expect(indexStatus).toBeVisible({ timeout: 60000 });
    await expect(indexStatus).not.toHaveText('🔄 初始化...', { timeout: 60000 });
    const text = await indexStatus.textContent();
    expect(text).toMatch(/\d+/);
  });
});

test.describe('BM25 Index', () => {
  test('BM25 index becomes ready', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loadingScreen')).toHaveClass(/hidden/, { timeout: 120000 });
    await page.waitForFunction(() => {
      const el = document.getElementById('modelStatus');
      return el && el.textContent && el.textContent.includes('BM25就绪');
    }, { timeout: 120000 });
    await expect(page.locator('#modelStatus')).toContainText('BM25就绪');
  });
});

test.describe('Search Functionality', () => {
  test('search triggers without error', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loadingScreen')).toHaveClass(/hidden/, { timeout: 120000 });
    await page.waitForFunction(() => {
      const el = document.getElementById('modelStatus');
      return el && el.textContent && el.textContent.includes('BM25就绪');
    }, { timeout: 120000 });
    
    // Ensure keyword mode is active
    const keywordBtn = page.locator('.mode-btn[data-mode="keyword"]');
    const keywordClass = await keywordBtn.getAttribute('class');
    if (!keywordClass || !keywordClass.includes('active')) {
      await keywordBtn.click();
      await page.waitForTimeout(500);
    }
    
    // Fill search input
    await page.locator('#searchInput').fill('python');
    await page.waitForTimeout(2000);
    
    // Verify search completed (either results or empty state shown)
    const hasResults = await page.locator('.repo-card').count() > 0;
    const hasEmpty = await page.locator('.empty').count() > 0;
    expect(hasResults || hasEmpty).toBeTruthy();
  });

  test('empty search shows no results', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loadingScreen')).toHaveClass(/hidden/, { timeout: 120000 });
    await page.waitForFunction(() => {
      const el = document.getElementById('modelStatus');
      return el && el.textContent && el.textContent.includes('BM25就绪');
    }, { timeout: 120000 });
    
    const keywordBtn = page.locator('.mode-btn[data-mode="keyword"]');
    const keywordClass = await keywordBtn.getAttribute('class');
    if (!keywordClass || !keywordClass.includes('active')) {
      await keywordBtn.click();
      await page.waitForTimeout(500);
    }
    
    await page.locator('#searchInput').fill('zzznonexistentrepo12345');
    await page.waitForTimeout(2000);
    
    await expect(page.locator('.empty')).toBeVisible({ timeout: 30000 });
  });

  test('Chinese search works', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loadingScreen')).toHaveClass(/hidden/, { timeout: 120000 });
    await page.waitForFunction(() => {
      const el = document.getElementById('modelStatus');
      return el && el.textContent && el.textContent.includes('BM25就绪');
    }, { timeout: 120000 });
    
    const keywordBtn = page.locator('.mode-btn[data-mode="keyword"]');
    const keywordClass = await keywordBtn.getAttribute('class');
    if (!keywordClass || !keywordClass.includes('active')) {
      await keywordBtn.click();
      await page.waitForTimeout(500);
    }
    
    await page.locator('#searchInput').fill('中文');
    await page.waitForTimeout(2000);
    
    await expect(page.locator('.results-list')).toBeVisible({ timeout: 30000 });
  });
});

test.describe('Mode Switching', () => {
  test('keyword mode is active by default', async ({ page }) => {
    await page.goto('/');
    await page.locator('#searchInput').waitFor({ state: 'visible', timeout: 60000 });
    const keywordBtn = page.locator('.mode-btn[data-mode="keyword"]');
    await expect(keywordBtn).toHaveClass(/active/);
  });

  test('clicking hybrid mode activates it', async ({ page }) => {
    await page.goto('/');
    await page.locator('#searchInput').waitFor({ state: 'visible', timeout: 60000 });
    const hybridBtn = page.locator('.mode-btn[data-mode="hybrid"]');
    await hybridBtn.click();
    await expect(hybridBtn).toHaveClass(/active/);
  });

  test('search tip is visible', async ({ page }) => {
    await page.goto('/');
    const searchTip = page.locator('#searchTip');
    await expect(searchTip).toBeVisible({ timeout: 60000 });
    const tipText = await searchTip.textContent();
    expect(tipText.length).toBeGreaterThan(0);
  });
});

test.describe('UI Elements', () => {
  test('filters bar is visible', async ({ page }) => {
    await page.goto('/');
    await page.locator('#searchInput').waitFor({ state: 'visible', timeout: 60000 });
    const filters = page.locator('.filters');
    await expect(filters).toBeVisible();
  });

  test('footer is visible', async ({ page }) => {
    await page.goto('/');
    await page.locator('#searchInput').waitFor({ state: 'visible', timeout: 60000 });
    const footer = page.locator('footer');
    await expect(footer).toBeVisible();
  });
});
