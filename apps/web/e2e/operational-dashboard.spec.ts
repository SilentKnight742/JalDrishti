import { expect, test } from "@playwright/test";

test("loads live Assam records and keeps facilities opt-in", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Assam evidence map" })).toBeVisible();
  await expect(page.getByText("System connected")).toBeVisible();

  const facilitiesLayer = page.getByRole("button", { name: "Facilities" });
  await expect(facilitiesLayer).toHaveAttribute("aria-pressed", "false");
  await facilitiesLayer.click();
  await expect(facilitiesLayer).toHaveAttribute("aria-pressed", "true");

  const recordPicker = page.getByLabel("Inspect mapped record");
  await expect(recordPicker.locator('optgroup[label="Districts"] option')).not.toHaveCount(0);
  await recordPicker.selectOption({ label: "Bajali" });

  await expect(page.getByRole("heading", { name: "Bajali" })).toBeVisible();
  await expect(page.getByText("District evidence")).toBeVisible();
  await expect(page.getByRole("button", { name: "Show all Assam" })).toBeVisible();
});

test("opens the mobile incident-reporting flow with its safety boundary", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.getByRole("button", { name: "Report incident" }).click();
  const dialog = page.getByRole("dialog", { name: "Report a flood incident" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("This does not dispatch emergency services.")).toBeVisible();
  await expect(dialog.getByText("call 112")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Submit unverified report" })).toBeDisabled();
  await dialog.getByRole("button", { name: "Close incident report" }).click();
  await expect(dialog).toBeHidden();
});
