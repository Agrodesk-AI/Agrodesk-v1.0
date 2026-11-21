import { test, expect } from "@playwright/test";

// Smoke test — assumes:
//   1. apps/api is running on http://localhost:8000 with a migrated DB
//   2. apps/web is running on http://localhost:3000 (`npm run dev`)
//   3. A platform-admin + a dealer with an owner user already exist; the
//      test logs in as that owner.
//
// Set E2E_OWNER_PHONE + E2E_OWNER_FIXED_CODE to a (phone, otp code pair)
// that your dev setup accepts. For a disposable dev loop, point the API's
// FakeSmsProvider at a captured log and read the code manually — the test
// expects you to pass it via env.

const PHONE = process.env.E2E_OWNER_PHONE ?? "9999900001";
const CODE = process.env.E2E_OWNER_FIXED_CODE ?? "";

test("Quick Add -> list -> transition", async ({ page }) => {
  test.skip(!CODE, "Set E2E_OWNER_FIXED_CODE to run this test");

  await page.goto("/login");
  await page.getByTestId("login-phone").fill(PHONE);
  await page.getByTestId("login-send").click();
  await page.getByTestId("login-code").fill(CODE);
  await page.getByTestId("login-verify").click();

  await page.waitForURL("**/today");

  await page.goto("/leads/new");
  const uniquePhone = "9876" + Date.now().toString().slice(-6);
  await page.getByTestId("qa-phone").fill(uniquePhone);
  await page.getByTestId("qa-name").fill("Playwright Ramesh");
  await page.getByTestId("qa-submit").click();

  await page.waitForURL(/\/leads\/[0-9a-f-]+/);
  await expect(page.getByTestId("lead-stage")).toContainText(/new/i);

  await page.getByTestId("open-transition").click();
  await page.locator('[data-stage="contacted"]').click();
  await page.getByTestId("transition-save").click();
  await expect(page.getByTestId("lead-stage")).toContainText(/contact/i);
});
