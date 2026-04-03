# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: test_9e4be516-d783-4a02-ae55-385f829a8809.spec.ts >> Test_2026-04-02
- Location: test_9e4be516-d783-4a02-ae55-385f829a8809.spec.ts:5:5

# Error details

```
Error: page.goto: Target page, context or browser has been closed
Call log:
  - navigating to "https://www.baidu.com/", waiting until "load"

```

# Test source

```ts
  1 | 
  2 | import { test } from '@playwright/test';
  3 | import { expect } from '@playwright/test';
  4 | 
  5 | test('Test_2026-04-02', async ({ page, context }) => {
  6 |   
  7 |     // Navigate to URL
> 8 |     await page.goto('https://www.baidu.com');
    |                ^ Error: page.goto: Target page, context or browser has been closed
  9 | });
```